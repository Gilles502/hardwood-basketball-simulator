import React from 'react';
import { normalizeRole } from '../../utils/roles';
import { ownerLabel } from '../../utils/owners';
import type { TeamFinancials } from './ContractsTab';

/** One player as /api/team-strategy-intel lists him in a tier. */
interface IntelPlayer {
  nome: string;
  ruolo: string;
  eta: number;
  ovr: number;
  salario: number;
  anni: number;
  tag?: string;
}

interface RoleNeed {
  count: number;
  avg_ovr: number;
  is_urgent_need: boolean;
  is_need: boolean;
  is_surplus: boolean;
}

export interface TeamIntel {
  team_name: string;
  team_state: string;
  owner_personality: string;
  direction_title: string;
  direction_description: string;
  role_breakdown?: Record<string, RoleNeed>;
  untouchables?: IntelPlayer[];
  key_starters?: IntelPlayer[];
  trade_block?: IntelPlayer[];
  tradeables?: IntelPlayer[];
  financials?: TeamFinancials & { salary_cap_space: number };
  draft_capital?: { firsts_count: number };
}

type Tier = 'lock' | 'core' | 'block';

interface StrategyTabProps {
  intel: TeamIntel;
  isOwnTeam: boolean;
  seasonLabel: string | null;
  onOpenPlayer: (name: string) => void;
  onTradeFor: (player: string) => void;
}

const POSITIONS = ['PG', 'SG', 'SF', 'PF', 'C'];

const TIER_LABEL: Record<Tier, string> = { lock: 'Untouchable', core: 'Core', block: 'On the block' };

const money = (value: number) => `$${value.toFixed(1)}M`;

/** Stamp colour by team state: building teams green, winning teams orange, the rest brown. */
const stampTone = (state: string) => {
  if (['Rebuilding', 'Rising Star'].includes(state)) return 'is-build';
  if (['Contender', 'Defending Champion', 'Playoff Team'].includes(state)) return 'is-win';
  return '';
};

const needOf = (need: RoleNeed | undefined): { tone: string; label: string } => {
  if (need?.is_urgent_need) return { tone: 'is-urgent', label: 'Main need' };
  if (need?.is_need) return { tone: 'is-upgrade', label: 'Upgrade' };
  if (need?.is_surplus) return { tone: 'is-surplus', label: 'Surplus' };
  return { tone: '', label: 'Solid' };
};

export const StrategyTab: React.FC<StrategyTabProps> = ({ intel, isOwnTeam, seasonLabel, onOpenPlayer, onTradeFor }) => {
  const block = intel.trade_block ?? intel.tradeables ?? [];
  const tiers: [Tier, IntelPlayer[]][] = [['lock', intel.untouchables ?? []], ['core', intel.key_starters ?? []], ['block', block]];
  const players = tiers.flatMap(([tier, list]) => list.map((p) => ({ ...p, tier })));

  const capSpace = intel.financials?.salary_cap_space ?? null;

  return (
    <div className="st-root">
      <div className="st-top">
        <div className="st-memo">
          <dl className="st-memo-head">
            <dt>From</dt><dd>{intel.team_name} front office</dd>
            <dt>Owner</dt><dd>{ownerLabel(intel.owner_personality)}</dd>
            <dt>Re</dt><dd>{seasonLabel ? `Direction for ${seasonLabel}` : 'Team direction'}</dd>
          </dl>
          <div className="st-memo-body">
            <div>
              <h2>{intel.direction_title}</h2>
              <p>{intel.direction_description}</p>
            </div>
            <span className={`st-stamp ${stampTone(intel.team_state)}`}>{intel.team_state}</span>
          </div>
        </div>
        <div className="st-facts">
          <div className="st-fact">
            <div><span className="rc-label">Cap space</span><span className="rc-note">{capSpace === null ? 'unavailable' : capSpace >= 0 ? 'under the cap' : 'over the cap'}</span></div>
            <b className={capSpace === null ? '' : capSpace >= 0 ? 'is-good' : 'is-bad'}>{capSpace === null ? '–' : money(Math.abs(capSpace))}</b>
          </div>
          <div className="st-fact">
            <div><span className="rc-label">1st-round picks</span><span className="rc-note">next 5 drafts</span></div>
            <b>{intel.draft_capital?.firsts_count ?? '–'}</b>
          </div>
          <div className="st-fact">
            <div><span className="rc-label">On the block</span><span className="rc-note">available now</span></div>
            <b className="is-good">{block.length}</b>
          </div>
        </div>
      </div>

      <div>
        <span className="rc-card-title">Depth chart · needs and availability</span>
        <div className="st-depth">
          {POSITIONS.map((pos) => {
            const need = needOf(intel.role_breakdown?.[pos]);
            const atPos = players.filter((p) => normalizeRole(p.ruolo) === pos).sort((a, b) => b.ovr - a.ovr);
            const avg = atPos.length ? Math.round(atPos.reduce((s, p) => s + p.ovr, 0) / atPos.length) : null;
            return (
              <section key={pos} className="st-pos" aria-label={`${pos}: ${need.label}`}>
                <div className={`st-pos-band ${need.tone}`}><b>{pos}</b><span>{need.label}</span></div>
                <div className="st-pos-meta"><span>{atPos.length} deep</span><span>{avg === null ? '–' : `avg ${avg}`}</span></div>
                {atPos.length === 0 && <div className="st-pos-empty">Nobody at {pos}</div>}
                {atPos.map((p) => (
                  <div key={p.nome} className={`st-player is-${p.tier}`}>
                    <div className="st-player-row">
                      <button type="button" className="st-player-name" onClick={() => onOpenPlayer(p.nome)}>
                        {p.tier === 'lock' && <span aria-hidden="true">🔒 </span>}{p.nome}
                      </button>
                      <span className="st-player-ovr">{p.ovr}</span>
                    </div>
                    <div className="st-player-row">
                      <small>{p.eta} · {money(p.salario)} · {p.anni}y</small>
                      <span className={`st-tier is-${p.tier}`}>{TIER_LABEL[p.tier]}</span>
                    </div>
                    {p.tag && p.tag !== TIER_LABEL[p.tier] && <small className="st-player-note">{p.tag}</small>}
                    {!isOwnTeam && p.tier !== 'lock' && (
                      <button type="button" className="st-trade" onClick={() => onTradeFor(p.nome)}>Trade for</button>
                    )}
                  </div>
                ))}
              </section>
            );
          })}
        </div>
        <div className="st-legend">
          <span><span className="st-tier is-lock">Untouchable</span> not for sale</span>
          <span><span className="st-tier is-core">Core</span> only for big offers</span>
          <span><span className="st-tier is-block">On the block</span> available now</span>
        </div>
      </div>
    </div>
  );
};
