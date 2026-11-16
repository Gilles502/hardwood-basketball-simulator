from typing import List, Dict, Any, Optional
import random
import logging
from core.models import Squadra
from trades.trade_finder import TradeFinder
from trades.trade_validator import TradeValidator

from core.config import CONFIG

main_log = logging.getLogger('main_sim')

class TradeBlockManager:
    @staticmethod
    def value_for_user(finder: Any, user_team: Squadra, user_gets: list, user_gives: list) -> Dict[str, float]:
        """What an offer is worth to the user's team in the trade engine's own points: received minus given,
        and the value given (the End of Season Hub reads the share gained or lost)."""
        gets = sum(finder.get_strategic_value(a, user_team) for a in user_gets)
        gives = sum(finder.get_strategic_value(a, user_team) for a in user_gives)
        return {"value_for_user": round(gets - gives, 1), "value_given": round(gives, 1)}

    @staticmethod
    def _offer_from(finder: Any, torneo: Any, user_team: Squadra, player: Any, partner: Squadra,
                    user_picks: list, shuffle_targets: bool = False) -> Optional[Dict[str, Any]]:
        """One offer from `partner` for a player on the user's block, or None. The CPU initiates the offer, so it
        must make sense for it: the partner needs a wish the deal fulfils (its plan question) and a price it likes."""
        if not finder.wishes_for(partner):
            return None   # a team with nothing on its wish list has no use for any player
        era = finder.era()
        filler_pay = era.money(8.0)
        partner_tradeables = finder.get_tradeable_players(partner, allow_stars=(player.ovr >= era.ovr_at(85)))
        if not partner_tradeables:
            return None

        partner_picks = finder._collect_team_picks(partner)
        partner_fillers = sorted((p for p in partner_tradeables if p.contract and p.contract.salario_annuale < filler_pay),
                                 key=lambda x: x.contract.salario_annuale)
        targets = [p for p in partner_tradeables if p.contract]
        if shuffle_targets:
            random.shuffle(targets)   # keeps offers fresh and unpredictable

        def salaries_match(give, get):
            salary_g = sum(p.contract.salario_annuale for p in give)
            salary_r = sum(p.contract.salario_annuale for p in get)
            return (user_team.check_trade_salary_match(salary_r, salary_g)[0]
                    and partner.check_trade_salary_match(salary_g, salary_r)[0])

        def roster_ok(team, net):
            return CONFIG.OFFSEASON.TRADE_ROSTER_MIN_SIZE <= len(team.roster) + net <= CONFIG.OFFSEASON.ROSTER_SIZE_LIMIT

        for target in targets:
            giving_players, receiving_players = [player], [target]
            if not salaries_match(giving_players, receiving_players):
                # a cheap filler from the user, else one from the partner
                with_filler = next(([player, f] for f in user_team.roster
                                    if f != player and f.contract and f.contract.salario_annuale < filler_pay
                                    and salaries_match([player, f], receiving_players)), None)
                with_return = next(([target, pf] for pf in partner_fillers
                                    if pf != target and salaries_match(giving_players, [target, pf])), None)
                giving_players = with_filler or giving_players
                receiving_players = receiving_players if with_filler else (with_return or receiving_players)
            if not salaries_match(giving_players, receiving_players):
                continue
            if not (roster_ok(user_team, len(receiving_players) - len(giving_players))
                    and roster_ok(partner, len(giving_players) - len(receiving_players))):
                continue

            # Picks make the value fair for both sides (the CPU should accept)
            giving_picks, receiving_picks = [], []

            def partner_accepts_check():
                return finder.would_accept_trade_with_reason(partner, giving_players + giving_picks,
                                                             receiving_players + receiving_picks)

            if not partner_accepts_check()[0]:
                # Partner needs more value: the user adds picks
                for py, pk in user_picks:
                    if len(giving_picks) >= 2:
                        break
                    if "R2" in pk and sum(1 for p in giving_picks if "R2" in p) >= 1:
                        continue
                    p_asset = f"{py}:{pk}"
                    if "R1" in pk and not TradeValidator.check_stepien_rule(torneo, user_team.nome, giving_picks + [p_asset])[0]:
                        continue
                    giving_picks.append(p_asset)
                    if partner_accepts_check()[0]:
                        break
            else:
                # Partner gets too much value: it adds picks
                val_user_gives = sum(finder.get_strategic_value(p, partner) for p in giving_players + giving_picks)
                val_partner_gives = sum(finder.get_strategic_value(p, partner) for p in receiving_players)
                if val_user_gives > val_partner_gives * 1.15:
                    for py, pk in partner_picks:
                        if len(receiving_picks) >= 2:
                            break
                        p_asset = f"{py}:{pk}"
                        if "R1" in pk and not TradeValidator.check_stepien_rule(torneo, partner.nome, receiving_picks + [p_asset])[0]:
                            continue
                        still_accepts, _ = finder.would_accept_trade_with_reason(
                            partner, giving_players + giving_picks, receiving_players + receiving_picks + [p_asset])
                        if not still_accepts:
                            break
                        receiving_picks.append(p_asset)
                        val_partner_gives = sum(finder.get_strategic_value(p, partner) for p in receiving_players + receiving_picks)
                        if val_user_gives <= val_partner_gives * 1.1:
                            break

            is_valid, _ = TradeValidator.validate_trade(user_team, partner, giving_players + giving_picks,
                                                        receiving_players + receiving_picks, torneo=torneo)
            if not is_valid or not partner_accepts_check()[0]:
                continue

            deal = finder.pair_deal(user_team, partner, giving_players + giving_picks, receiving_players + receiving_picks)
            return {
                "id": f"block-offer-{partner.nome.replace(' ', '-').lower()}-{random.randint(1000, 9999)}",
                "offering_team": partner.nome,
                "receiving_team": user_team.nome,
                "giving_players": TradeBlockManager._serialize(receiving_players),  # the partner gives these to the user
                "receiving_players": TradeBlockManager._serialize(giving_players),  # the partner gets these from the user
                "giving_picks": receiving_picks,  # Partner gives to user
                "receiving_picks": giving_picks,  # Partner gets from user
                "why": finder.user_motive(deal).why,
                **TradeBlockManager.value_for_user(finder, user_team, receiving_players + receiving_picks,
                                                   giving_players + giving_picks),
            }
        return None

    @staticmethod
    def _serialize(players: list) -> List[Dict[str, Any]]:
        return [{
            "name": p.nome,
            "ovr": p.ovr,
            "position": p.ruolo,
            "age": p.eta,
            "salary": p.contract.salario_annuale if p.contract else 0,
            "contract_years": p.contract.anni_rimanenti if p.contract else 0
        } for p in players]

    @staticmethod
    def generate_offers(torneo: Any, user_team: Squadra) -> List[Dict[str, Any]]:
        """
        Scans the user team's players marked with `on_trade_block = True` and generates valid trade offers
        (up to 2 per player) from the CPU teams that have a wish the player fulfils, each with its `why`.
        """
        finder = TradeFinder(torneo, torneo.squadre, user_team)
        block_players = [p for p in user_team.roster if getattr(p, 'on_trade_block', False)]
        if not block_players:
            return []

        new_offers = []
        user_picks = finder._collect_team_picks(user_team)
        for player in block_players:
            # Shuffle so we get diverse offers on different generations
            partners = [t for t in torneo.squadre if t.nome != user_team.nome]
            random.shuffle(partners)
            offers_for_this_player = 0
            for partner in partners:
                if offers_for_this_player >= 2:  # Limit of 2 offers per player to keep list clean
                    break
                offer = TradeBlockManager._offer_from(finder, torneo, user_team, player, partner, user_picks)
                if offer:
                    new_offers.append(offer)
                    offers_for_this_player += 1
        return new_offers

    @staticmethod
    def generate_offer_for_simulation(torneo: Any, user_team: Squadra) -> Optional[Dict[str, Any]]:
        """
        Generates a single trade block offer for a random player on the user's trade block.
        Returns the offer dict if generated, otherwise None.
        """
        finder = TradeFinder(torneo, torneo.squadre, user_team)
        block_players = [p for p in user_team.roster if getattr(p, 'on_trade_block', False)]
        if not block_players:
            return None

        player = random.choice(block_players)
        partners = [t for t in torneo.squadre if t.nome != user_team.nome]
        random.shuffle(partners)
        user_picks = finder._collect_team_picks(user_team)
        for partner in partners:
            offer = TradeBlockManager._offer_from(finder, torneo, user_team, player, partner, user_picks, shuffle_targets=True)
            if offer:
                return offer
        return None
