// File: frontend/src/pages/Trades.tsx
import React, { useState, useEffect, useRef } from 'react';
import { useLeagueStore } from '../store/leagueStore';
import { Check, X, ShieldAlert, MessageSquare, DollarSign, Briefcase } from 'lucide-react';
import { TradeHistoryLog } from '../components/TradeHistoryLog';
import { DashboardTabs } from '../components/DashboardTabs';
import { TeamCrest } from '../components/TeamCrest';
import { crestLabel } from '../utils/crest';
import { normalizeRole } from '../utils/roles';
import { TradeRosterTable } from './trades/TradeRosterTable';
import { TradeFinderPanel } from './trades/TradeFinderPanel';
import { TradeBlockPanel } from './trades/TradeBlockPanel';
import type { PlayerAsset, PickAsset, TeamAssets, TradeOffer, TradeBlockOffer } from './trades/types';
import './dashboard/Dashboard.css'; // dash-header / dash-tabs, shared with the Dashboard
import './trades/TradeMachine.css';
import './trades/TradeTabs.css';

const formatPosition = (pos?: string): string => normalizeRole(pos);

interface ValidationResult {
  is_valid: boolean;
  validation_message: string;
  ai_accepted: boolean;
  ai_reason: string;
  why?: string;
}

interface CounterOfferResult {
  has_counter: boolean;
  message: string;
  add_user_players: string[];
  add_user_picks: string[];
  modified_protections: Record<string, string>;
  will_accept_counter?: boolean;
  accepted_as_is?: boolean;
  why?: string;
}

/** A player to open the Trade Machine on (from "Trade for" on the Strategy tab). */
export interface TradeTarget {
  team: string;
  player: string;
}

interface TradesProps {
  initialTarget?: TradeTarget | null;
}

export const Trades: React.FC<TradesProps> = ({ initialTarget = null }) => {
  const { leagueData, fetchLeagueData } = useLeagueStore();
  const [activeSubTab, setActiveSubTab] = useState<'machine' | 'finder' | 'block' | 'history'>('machine');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // -------------------------------------------------------------
  // STATE FOR SUB-TAB: TRADE MACHINE (2-Team & 3-Team)
  // -------------------------------------------------------------
  const [tradeMode, setTradeMode] = useState<'2-team' | '3-team'>('2-team');
  const [partnerTeam, setPartnerTeam] = useState<string>(initialTarget?.team ?? '');
  // Selected once the partner's assets arrive, so the reset in fetchCustomTradeAssets doesn't wipe it.
  const pendingPartnerPlayer = useRef<string | null>(initialTarget?.player ?? null);
  const [teamC, setTeamC] = useState<string>('');
  const [threeTeamView, setThreeTeamView] = useState<'A' | 'B' | 'C'>('A');
  
  const [userAssets, setUserAssets] = useState<TeamAssets>({ players: [], picks: [] });
  const [partnerAssets, setPartnerAssets] = useState<TeamAssets>({ players: [], picks: [] });
  const [teamCAssets, setTeamCAssets] = useState<TeamAssets>({ players: [], picks: [] });
  
  // Selected 2-Team trade items
  const [selectedUserPlayers, setSelectedUserPlayers] = useState<string[]>([]);
  const [selectedUserPicks, setSelectedUserPicks] = useState<string[]>([]);
  const [selectedPartnerPlayers, setSelectedPartnerPlayers] = useState<string[]>([]);
  const [selectedPartnerPicks, setSelectedPartnerPicks] = useState<string[]>([]);
  const [userPickProtections, setUserPickProtections] = useState<Record<string, string>>({});
  const [partnerPickProtections, setPartnerPickProtections] = useState<Record<string, string>>({});
  
  // Selected 3-Team routing
  // Team A assets routing: { playerName: 'B' | 'C', pickKey: 'B' | 'C' }
  const [aRouting, setARouting] = useState<Record<string, 'B' | 'C'>>({});
  // Team B assets routing: { playerName: 'A' | 'C', pickKey: 'A' | 'C' }
  const [bRouting, setBRouting] = useState<Record<string, 'A' | 'C'>>({});
  // Team C assets routing: { playerName: 'A' | 'B', pickKey: 'A' | 'B' }
  const [cRouting, setCRouting] = useState<Record<string, 'A' | 'B'>>({});
  
  // 3-Team Validation Result
  const [validation3Team, setValidation3Team] = useState<{
    is_valid: boolean;
    validation_message: string;
    team_b?: { name: string; accepted: boolean; reason: string };
    team_c?: { name: string; accepted: boolean; reason: string };
    status_by_team?: Record<string, any>;
    all_accepted: boolean;
  } | null>(null);

  // 2-Team Validation status & Counter Offer State
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [isTradeWindowOpen, setIsTradeWindowOpen] = useState(true);
  const [tradeWindowMessage, setTradeWindowMessage] = useState('');
  const [leagueState, setLeagueState] = useState('');
  
  const [counterOffer, setCounterOffer] = useState<CounterOfferResult | null>(null);
  const [counterLoading, setCounterLoading] = useState<boolean>(false);
  const [showCounterModal, setShowCounterModal] = useState<boolean>(false);

  // -------------------------------------------------------------
  // STATE FOR SUB-TAB: TRADE FINDER (Multi-Asset Custom Package)
  // -------------------------------------------------------------
  const [tradeablePlayers, setTradeablePlayers] = useState<PlayerAsset[]>([]);
  const [tradeablePicks, setTradeablePicks] = useState<PickAsset[]>([]);
  const [finderSelectedPlayers, setFinderSelectedPlayers] = useState<string[]>([]);
  const [finderSelectedPicks, setFinderSelectedPicks] = useState<string[]>([]);
  const [finderOffers, setFinderOffers] = useState<TradeOffer[]>([]);
  const [finderFilterMode, setFinderFilterMode] = useState<'all' | '2-team' | '3-team' | 'multi-team'>('all');
  const [targetNeedRole, setTargetNeedRole] = useState<string>('all');
  const [minNeedOvr, setMinNeedOvr] = useState<number>(76);
  const [needSearchLoading, setNeedSearchLoading] = useState<boolean>(false);

  // What Would It Take State
  const [showWhatWouldItTakeModal, setShowWhatWouldItTakeModal] = useState<boolean>(false);
  const [whatWouldItTakeTarget, setWhatWouldItTakeTarget] = useState<string>('');
  const [whatWouldItTakeResult, setWhatWouldItTakeResult] = useState<any | null>(null);
  const [whatWouldItTakeLoading, setWhatWouldItTakeLoading] = useState<boolean>(false);

  // -------------------------------------------------------------
  // STATE FOR SUB-TAB: TRADE BLOCK
  // -------------------------------------------------------------
  const [blockOffers, setBlockOffers] = useState<TradeBlockOffer[]>([]);
  const [blockLoading, setBlockLoading] = useState(false);

  useEffect(() => {
    if (!leagueData) {
      fetchLeagueData();
    }
  }, [leagueData, fetchLeagueData]);

  // Load Custom Trade Assets when partner team changes
  const fetchCustomTradeAssets = async (pTeamName: string, tCName?: string) => {
    if (!pTeamName) {
      setUserAssets({ players: [], picks: [] });
      setPartnerAssets({ players: [], picks: [] });
      setValidation(null);
      setCounterOffer(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/user-trade-info?partner_team=${pTeamName}&_t=${Date.now()}`);
      const data = await response.json();
      if (data.error) {
        setError(data.error);
      } else {
        setUserAssets(data.player_team_assets || { players: [], picks: [] });
        setPartnerAssets(data.partner_team_assets || { players: [], picks: [] });
        setIsTradeWindowOpen(data.trade_window_open);
        setTradeWindowMessage(data.trade_window_message || '');
        setLeagueState(data.league_state);
        
        // Kept (not consumed) so a repeated load of the same partner still selects him.
        const pending = pTeamName === initialTarget?.team ? pendingPartnerPlayer.current : null;
        const partnerPlayers: PlayerAsset[] = data.partner_team_assets?.players || [];
        setSelectedUserPlayers([]);
        setSelectedUserPicks([]);
        setSelectedPartnerPlayers(pending && partnerPlayers.some((p) => p.name === pending) ? [pending] : []);
        setSelectedPartnerPicks([]);
        setUserPickProtections({});
        setPartnerPickProtections({});
        setValidation(null);
        setCounterOffer(null);
      }
      
      // If team C provided in 3-team mode
      if (tCName) {
        const respC = await fetch(`/api/user-trade-info?partner_team=${tCName}&_t=${Date.now()}`);
        const dataC = await respC.json();
        if (dataC.partner_team_assets) {
          setTeamCAssets(dataC.partner_team_assets);
        }
      }
    } catch (err) {
      setError('Unable to load the teams\' assets.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (activeSubTab === 'machine') {
      fetchCustomTradeAssets(partnerTeam);
    } else if (activeSubTab === 'finder') {
      fetchFinderAssets();
    } else if (activeSubTab === 'block') {
      fetchBlockOffers();
    }
  }, [activeSubTab, partnerTeam]);

  // Once the user picks another partner, the "Trade for" player no longer applies.
  useEffect(() => {
    if (partnerTeam !== initialTarget?.team) pendingPartnerPlayer.current = null;
  }, [partnerTeam, initialTarget]);

  const fetchFinderAssets = async () => {
    setLoading(true);
    try {
      const response = await fetch(`/api/tradeable-players?_t=${Date.now()}`);
      const data = await response.json();
      setTradeablePlayers(data.players || []);
      setTradeablePicks(data.picks || []);
      setFinderSelectedPlayers([]);
      setFinderSelectedPicks([]);
      setFinderOffers([]);
    } catch (err) {
      console.error('Failed to load tradeable assets:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchBlockOffers = async () => {
    setBlockLoading(true);
    try {
      const response = await fetch(`/api/trade-block/offers?_t=${Date.now()}`);
      const data = await response.json();
      setBlockOffers(data.offers || []);
    } catch (err) {
      console.error('Failed to load trade block offers:', err);
    } finally {
      setBlockLoading(false);
    }
  };

  // Trade validation effect
  useEffect(() => {
    const validateTrade = async () => {
      if (
        !partnerTeam ||
        (selectedUserPlayers.length === 0 &&
          selectedUserPicks.length === 0 &&
          selectedPartnerPlayers.length === 0 &&
          selectedPartnerPicks.length === 0)
      ) {
        setValidation(null);
        return;
      }

      const completeUserProtections: Record<string, string> = { ...userPickProtections };
      selectedUserPicks.forEach(pk => {
        if (!completeUserProtections[pk]) {
          const found = userAssets.picks.find(p => p.key === pk);
          completeUserProtections[pk] = found?.protection || 'Unprotected';
        }
      });

      const completePartnerProtections: Record<string, string> = { ...partnerPickProtections };
      selectedPartnerPicks.forEach(pk => {
        if (!completePartnerProtections[pk]) {
          const found = partnerAssets.picks.find(p => p.key === pk);
          completePartnerProtections[pk] = found?.protection || 'Unprotected';
        }
      });

      try {
        const response = await fetch('/api/validate-user-trade', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            partner_team: partnerTeam,
            giving_players: selectedUserPlayers,
            giving_picks: selectedUserPicks,
            giving_pick_protections: completeUserProtections,
            receiving_players: selectedPartnerPlayers,
            receiving_picks: selectedPartnerPicks,
            receiving_pick_protections: completePartnerProtections
          })
        });
        const data = await response.json();
        // During a live sim run the server refuses (409): no verdict, the run bar says why.
        if (data.sim_running) { setValidation(null); return; }
        setValidation({
          is_valid: data.is_valid,
          validation_message: data.validation_message,
          ai_accepted: data.ai_accepted,
          ai_reason: data.ai_reason,
          why: data.why
        });
      } catch (err) {
        console.error('Trade validation failed:', err);
      }
    };

    const timeout = setTimeout(validateTrade, 300);
    return () => clearTimeout(timeout);
  }, [
    tradeMode,
    partnerTeam,
    selectedUserPlayers,
    selectedUserPicks,
    userPickProtections,
    selectedPartnerPlayers,
    selectedPartnerPicks,
    partnerPickProtections
  ]);

  // 3-Team validation effect
  useEffect(() => {
    if (tradeMode !== '3-team') return;
    if (!partnerTeam || !teamC) {
      setValidation3Team(null);
      return;
    }

    const a_to_b_players: string[] = [];
    const a_to_c_players: string[] = [];
    const a_to_b_picks: string[] = [];
    const a_to_c_picks: string[] = [];

    Object.entries(aRouting).forEach(([k, dest]) => {
      const isPlayer = userAssets.players.some(p => p.name === k);
      if (isPlayer) {
        if (dest === 'B') a_to_b_players.push(k);
        else if (dest === 'C') a_to_c_players.push(k);
      } else {
        if (dest === 'B') a_to_b_picks.push(k);
        else if (dest === 'C') a_to_c_picks.push(k);
      }
    });

    const b_to_a_players: string[] = [];
    const b_to_c_players: string[] = [];
    const b_to_a_picks: string[] = [];
    const b_to_c_picks: string[] = [];

    Object.entries(bRouting).forEach(([k, dest]) => {
      const isPlayer = partnerAssets.players.some(p => p.name === k);
      if (isPlayer) {
        if (dest === 'A') b_to_a_players.push(k);
        else if (dest === 'C') b_to_c_players.push(k);
      } else {
        if (dest === 'A') b_to_a_picks.push(k);
        else if (dest === 'C') b_to_c_picks.push(k);
      }
    });

    const c_to_a_players: string[] = [];
    const c_to_b_players: string[] = [];
    const c_to_a_picks: string[] = [];
    const c_to_b_picks: string[] = [];

    Object.entries(cRouting).forEach(([k, dest]) => {
      const isPlayer = teamCAssets.players.some(p => p.name === k);
      if (isPlayer) {
        if (dest === 'A') c_to_a_players.push(k);
        else if (dest === 'B') c_to_b_players.push(k);
      } else {
        if (dest === 'A') c_to_a_picks.push(k);
        else if (dest === 'B') c_to_b_picks.push(k);
      }
    });

    const totalAssets = a_to_b_players.length + a_to_c_players.length + a_to_b_picks.length + a_to_c_picks.length +
      b_to_a_players.length + b_to_c_players.length + b_to_a_picks.length + b_to_c_picks.length +
      c_to_a_players.length + c_to_b_players.length + c_to_a_picks.length + c_to_b_picks.length;

    if (totalAssets === 0) {
      setValidation3Team(null);
      return;
    }

    const runValidation3 = async () => {
      try {
        const resp = await fetch('/api/validate-3-team-trade', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            team_b: partnerTeam,
            team_c: teamC,
            trade_data: {
              a_to_b_players, a_to_b_picks, a_to_c_players, a_to_c_picks,
              b_to_a_players, b_to_a_picks, b_to_c_players, b_to_c_picks,
              c_to_a_players, c_to_a_picks, c_to_b_players, c_to_b_picks
            },
            pick_protections: {}
          })
        });
        const data = await resp.json();
        setValidation3Team(data.sim_running ? null : data);
      } catch (e) {
        console.error('3-team validation failed:', e);
      }
    };

    const timeout = setTimeout(runValidation3, 350);
    return () => clearTimeout(timeout);
  }, [tradeMode, partnerTeam, teamC, aRouting, bRouting, cRouting]);

  // Handle Request Counter Offer (Ribatti)
  const handleRequestCounterOffer = async () => {
    if (!partnerTeam) return;
    setCounterLoading(true);
    setError(null);

    const completeUserProtections: Record<string, string> = { ...userPickProtections };
    selectedUserPicks.forEach(pk => {
      if (!completeUserProtections[pk]) {
        const found = userAssets.picks.find(p => p.key === pk);
        completeUserProtections[pk] = found?.protection || 'Unprotected';
      }
    });

    const completePartnerProtections: Record<string, string> = { ...partnerPickProtections };
    selectedPartnerPicks.forEach(pk => {
      if (!completePartnerProtections[pk]) {
        const found = partnerAssets.picks.find(p => p.key === pk);
        completePartnerProtections[pk] = found?.protection || 'Unprotected';
      }
    });

    try {
      const response = await fetch('/api/counter-offer-trade', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          partner_team: partnerTeam,
          giving_players: selectedUserPlayers,
          giving_picks: selectedUserPicks,
          giving_pick_protections: completeUserProtections,
          receiving_players: selectedPartnerPlayers,
          receiving_picks: selectedPartnerPicks,
          receiving_pick_protections: completePartnerProtections
        })
      });
      const data = await response.json();
      if (data.error) {
        setError(data.error);
      } else {
        setCounterOffer(data);
        setShowCounterModal(true);
      }
    } catch (err) {
      setError('Error calculating counter-offer.');
    } finally {
      setCounterLoading(false);
    }
  };

  // Apply Counter Offer to selections
  const handleApplyCounterOffer = () => {
    if (!counterOffer) return;
    if (counterOffer.add_user_players && counterOffer.add_user_players.length > 0) {
      setSelectedUserPlayers(prev => Array.from(new Set([...prev, ...counterOffer.add_user_players])));
    }
    if (counterOffer.add_user_picks && counterOffer.add_user_picks.length > 0) {
      setSelectedUserPicks(prev => Array.from(new Set([...prev, ...counterOffer.add_user_picks])));
    }
    if (counterOffer.modified_protections && Object.keys(counterOffer.modified_protections).length > 0) {
      setUserPickProtections(prev => ({ ...prev, ...counterOffer.modified_protections }));
      setPartnerPickProtections(prev => ({ ...prev, ...counterOffer.modified_protections }));
    }
    setShowCounterModal(false);
    setSuccessMessage('Counter-offer applied to trade! The CPU will automatically reconsider.');
    setTimeout(() => setSuccessMessage(null), 5000);
  };

  // Execute 2-team trade
  const handleExecuteTrade = async () => {
    if (!validation?.is_valid || !validation?.ai_accepted) return;
    setLoading(true);
    setError(null);

    const completeUserProtections: Record<string, string> = { ...userPickProtections };
    selectedUserPicks.forEach(pk => {
      if (!completeUserProtections[pk]) {
        const found = userAssets.picks.find(p => p.key === pk);
        completeUserProtections[pk] = found?.protection || 'Unprotected';
      }
    });

    const completePartnerProtections: Record<string, string> = { ...partnerPickProtections };
    selectedPartnerPicks.forEach(pk => {
      if (!completePartnerProtections[pk]) {
        const found = partnerAssets.picks.find(p => p.key === pk);
        completePartnerProtections[pk] = found?.protection || 'Unprotected';
      }
    });

    try {
      const response = await fetch('/api/execute-user-trade', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          partner_team: partnerTeam,
          giving_players: selectedUserPlayers,
          giving_picks: selectedUserPicks,
          giving_pick_protections: completeUserProtections,
          receiving_players: selectedPartnerPlayers,
          receiving_picks: selectedPartnerPicks,
          receiving_pick_protections: completePartnerProtections
        })
      });
      const data = await response.json();
      if (data.error) {
        setError(data.error);
      } else {
        setSuccessMessage('Trade completed successfully!');
        fetchCustomTradeAssets(partnerTeam);
        fetchLeagueData();
        setTimeout(() => setSuccessMessage(null), 5000);
      }
    } catch (err) {
      setError('Communication error while executing trade.');
    } finally {
      setLoading(false);
    }
  };

  // Execute 3-team trade
  const handleExecute3TeamTrade = async () => {
    if (!validation3Team?.all_accepted) return;
    setLoading(true);
    setError(null);

    const a_to_b_players = Object.entries(aRouting).filter(([k, d]) => d === 'B' && userAssets.players.some(p => p.name === k)).map(([k]) => k);
    const a_to_c_players = Object.entries(aRouting).filter(([k, d]) => d === 'C' && userAssets.players.some(p => p.name === k)).map(([k]) => k);
    const a_to_b_picks = Object.entries(aRouting).filter(([k, d]) => d === 'B' && !userAssets.players.some(p => p.name === k)).map(([k]) => k);
    const a_to_c_picks = Object.entries(aRouting).filter(([k, d]) => d === 'C' && !userAssets.players.some(p => p.name === k)).map(([k]) => k);

    const b_to_a_players = Object.entries(bRouting).filter(([k, d]) => d === 'A' && partnerAssets.players.some(p => p.name === k)).map(([k]) => k);
    const b_to_c_players = Object.entries(bRouting).filter(([k, d]) => d === 'C' && partnerAssets.players.some(p => p.name === k)).map(([k]) => k);
    const b_to_a_picks = Object.entries(bRouting).filter(([k, d]) => d === 'A' && !partnerAssets.players.some(p => p.name === k)).map(([k]) => k);
    const b_to_c_picks = Object.entries(bRouting).filter(([k, d]) => d === 'C' && !partnerAssets.players.some(p => p.name === k)).map(([k]) => k);

    const c_to_a_players = Object.entries(cRouting).filter(([k, d]) => d === 'A' && teamCAssets.players.some(p => p.name === k)).map(([k]) => k);
    const c_to_b_players = Object.entries(cRouting).filter(([k, d]) => d === 'B' && teamCAssets.players.some(p => p.name === k)).map(([k]) => k);
    const c_to_a_picks = Object.entries(cRouting).filter(([k, d]) => d === 'A' && !teamCAssets.players.some(p => p.name === k)).map(([k]) => k);
    const c_to_b_picks = Object.entries(cRouting).filter(([k, d]) => d === 'B' && !teamCAssets.players.some(p => p.name === k)).map(([k]) => k);

    try {
      const response = await fetch('/api/execute-3-team-trade', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          team_b: partnerTeam,
          team_c: teamC,
          trade_data: {
            a_to_b_players, a_to_b_picks, a_to_c_players, a_to_c_picks,
            b_to_a_players, b_to_a_picks, b_to_c_players, b_to_c_picks,
            c_to_a_players, c_to_a_picks, c_to_b_players, c_to_b_picks
          },
          pick_protections: {}
        })
      });
      const data = await response.json();
      if (data.error) {
        setError(data.error);
      } else {
        setSuccessMessage(data.message || '3-team blockbuster trade completed!');
        fetchCustomTradeAssets(partnerTeam, teamC);
        fetchLeagueData();
        setARouting({});
        setBRouting({});
        setCRouting({});
        setTimeout(() => setSuccessMessage(null), 5000);
      }
    } catch (err) {
      setError('Error executing 3-team trade.');
    } finally {
      setLoading(false);
    }
  };

  // Trade Finder actions (Multi-Asset Custom Package)
  const handleSearchFinderTrades = async () => {
    if (finderSelectedPlayers.length === 0 && finderSelectedPicks.length === 0) {
      setError('Select at least one player or draft pick for your trade package.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/trade-finder', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          giving_players: finderSelectedPlayers,
          giving_picks: finderSelectedPicks,
          include_3_team: true,
          include_chains: true,
          target_position: targetNeedRole !== 'all' ? targetNeedRole : undefined,
          trade_mode_filter: finderFilterMode
        })
      });
      const data = await response.json();
      if (data.error) {
        setError(data.error);
        setFinderOffers([]);
      } else {
        setFinderOffers(data.trades || []);
      }
    } catch (err) {
      setError('Error fetching trade proposals.');
    } finally {
      setLoading(false);
    }
  };

  const handleSearchByNeed = async () => {
    if (targetNeedRole === 'all') {
      handleSearchFinderTrades();
      return;
    }
    setNeedSearchLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/trades/search-by-need', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_position: targetNeedRole,
          min_ovr: minNeedOvr
        })
      });
      const data = await response.json();
      if (data.error) {
        setError(data.error);
      } else {
        const combined = [
          ...(data.three_team || []),
          ...(data.two_team || [])
        ];
        setFinderOffers(combined);
      }
    } catch (err) {
      setError('Error searching by positional need.');
    } finally {
      setNeedSearchLoading(false);
    }
  };

  const handleLoadOfferIntoMachine = (offer: TradeOffer) => {
    setTradeMode('2-team');
    setPartnerTeam(offer.partner_team);
    setActiveSubTab('machine');
    setTimeout(() => {
      if (offer.giving_players) {
        setSelectedUserPlayers(offer.giving_players.map(p => p.name));
      }
      if (offer.giving_picks) {
        setSelectedUserPicks(offer.giving_picks);
      }
      if (offer.receiving_players) {
        setSelectedPartnerPlayers(offer.receiving_players.map(p => p.name));
      }
      if (offer.receiving_picks) {
        setSelectedPartnerPicks(offer.receiving_picks);
      }
    }, 400);
  };

  const handleLoad3TeamIntoMachine = (offer: TradeOffer) => {
    setTradeMode('3-team');
    setPartnerTeam(offer.partner_team);
    if (offer.third_team) {
      setTeamC(offer.third_team);
      fetchCustomTradeAssets(offer.partner_team, offer.third_team);
    }
    setActiveSubTab('machine');
  };

  const handleAcceptFinderOffer = async (offer: TradeOffer) => {
    setLoading(true);
    setError(null);
    try {
      const givingPlayers = (offer.giving_players || []).map((p) => p.name);
      const givingPicks = offer.giving_picks || [];
      const receivingPlayers = (offer.receiving_players || []).map((p) => p.name);
      const receivingPicks = offer.receiving_picks || [];

      const response = await fetch('/api/execute-user-trade', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          partner_team: offer.partner_team,
          giving_players: givingPlayers,
          giving_picks: givingPicks,
          giving_pick_protections: {},
          receiving_players: receivingPlayers,
          receiving_picks: receivingPicks,
          receiving_pick_protections: {}
        })
      });
      const data = await response.json();
      if (data.error) {
        setError(data.error);
      } else {
        setSuccessMessage(`Deal finalized with the ${offer.partner_team}! Trade completed.`);
        fetchFinderAssets();
        fetchLeagueData();
        setTimeout(() => setSuccessMessage(null), 5000);
      }
    } catch (err) {
      setError('Error accepting trade.');
    } finally {
      setLoading(false);
    }
  };

  const handleAccept3TeamFinderOffer = async (offer: TradeOffer) => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/execute-3-team-trade', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(offer.full_trade_payload ? {
          trade_data: offer.full_trade_payload,
          team_b: offer.partner_team,
          team_c: offer.third_team
        } : {
          full_payload: offer
        })
      });
      const data = await response.json();
      if (data.error) {
        setError(data.error);
      } else {
        setSuccessMessage(`3-team blockbuster trade finalized successfully with ${offer.partner_team} and ${offer.third_team}!`);
        fetchFinderAssets();
        fetchLeagueData();
        setTimeout(() => setSuccessMessage(null), 5000);
      }
    } catch (err) {
      setError('Error executing 3-team trade.');
    } finally {
      setLoading(false);
    }
  };

  const handleAccept4TeamFinderOffer = async (offer: any) => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/trades/execute-4-team', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          raw_trade_data: offer.raw_trade_data,
          flow: offer.flow
        })
      });
      const data = await response.json();
      if (data.error) {
        setError(data.error);
      } else {
        setSuccessMessage(data.message || `4-team mega-blockbuster completed successfully!`);
        fetchFinderAssets();
        fetchLeagueData();
        setTimeout(() => setSuccessMessage(null), 5000);
      }
    } catch (err) {
      setError('Error executing 4-team mega-blockbuster trade.');
    } finally {
      setLoading(false);
    }
  };

  const handleCalculateWhatWouldItTake = async (targetName: string) => {
    if (!targetName) return;
    setWhatWouldItTakeLoading(true);
    setWhatWouldItTakeResult(null);
    try {
      const response = await fetch('/api/trades/what-would-it-take', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ player_name: targetName })
      });
      const data = await response.json();
      setWhatWouldItTakeResult(data);
    } catch (err) {
      setWhatWouldItTakeResult({ attainable: false, reason: 'Server connection error' });
    } finally {
      setWhatWouldItTakeLoading(false);
    }
  };

  // Trade Block Actions
  const handleToggleTradeBlock = async (pName: string) => {
    try {
      const response = await fetch('/api/trade-block/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ player_name: pName })
      });
      const data = await response.json();
      if (data.success) {
        fetchLeagueData();
      }
    } catch (err) {
      console.error('Error toggling trade block:', err);
    }
  };

  const handleGenerateBlockOffers = async () => {
    setBlockLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/trade-block/generate', { method: 'POST' });
      const data = await response.json();
      if (data.error) {
        setError(data.error);
      } else {
        setBlockOffers(data.offers || []);
        setSuccessMessage('New Trade Block offers generated!');
        setTimeout(() => setSuccessMessage(null), 4000);
      }
    } catch (err) {
      setError('Error generating Trade Block offers.');
    } finally {
      setBlockLoading(false);
    }
  };

  const handleRespondBlockOffer = async (id: string, action: 'ACCEPT' | 'DECLINE') => {
    setBlockLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/trade-block/respond', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ offer_id: id, action })
      });
      const data = await response.json();
      if (data.error) {
        setError(data.error);
      } else {
        setSuccessMessage(action === 'ACCEPT' ? 'Trade accepted and executed!' : 'Offer declined.');
        fetchBlockOffers();
        fetchLeagueData();
        setTimeout(() => setSuccessMessage(null), 4000);
      }
    } catch (err) {
      setError('Unable to respond to offer.');
    } finally {
      setBlockLoading(false);
    }
  };

  const totalOutgoingSalary = selectedUserPlayers.reduce((sum, name) => {
    const player = userAssets.players.find((p) => p.name === name);
    return sum + (player?.salary || 0);
  }, 0);

  const totalIncomingSalary = selectedPartnerPlayers.reduce((sum, name) => {
    const player = partnerAssets.players.find((p) => p.name === name);
    return sum + (player?.salary || 0);
  }, 0);

  const netSalaryDiff = totalIncomingSalary - totalOutgoingSalary;

  // -------------------------------------------------------------
  // Trade Machine view helpers
  // -------------------------------------------------------------
  const userTeamName = leagueData?.player_team_name || '';
  const otherTeams = (leagueData?.league_database?.teams || []).filter((t) => t.nome !== userTeamName);

  const renderTeamPicker = (label: string, value: string, exclude: string, onPick: (name: string) => void) => (
    <label className="tm-team">
      {value ? <TeamCrest name={value} size={38} /> : <span className="tm-crest-empty" aria-hidden="true" />}
      <span>
        <span className="tm-team-label">{label}</span>
        <select className="tm-select" value={value} onChange={(e) => onPick(e.target.value)}>
          <option value="">Choose a team</option>
          {otherTeams.filter((t) => t.nome !== exclude).map((t) => (
            <option key={t.nome} value={t.nome}>{t.nome}</option>
          ))}
        </select>
      </span>
    </label>
  );

  const renderChip = (key: string, label: string, detail: string, onRemove: () => void) => (
    <span key={key} className="tm-chip">
      {label}{detail && <small>{detail}</small>}
      <button type="button" aria-label={`Remove ${label}`} onClick={onRemove}><X size={14} /></button>
    </span>
  );

  const formatMoney = (millions: number): string => `$${millions.toFixed(1)}M`;
  const netLabel = `${netSalaryDiff > 0 ? '+' : netSalaryDiff < 0 ? '−' : ''}${formatMoney(Math.abs(netSalaryDiff))}`;

  // 3-team: one entry per franchise, with the routing state that belongs to it
  const routeToggle = (setter: React.Dispatch<React.SetStateAction<Record<string, any>>>) =>
    (key: string, code: string) =>
      setter((prev) => {
        const next = { ...prev };
        if (next[key] === code) delete next[key];
        else next[key] = code;
        return next;
      });

  const threeTeams = [
    { code: 'A', name: userTeamName, assets: userAssets, routing: aRouting as Record<string, string | undefined>, route: routeToggle(setARouting), accent: 'you' as const },
    { code: 'B', name: partnerTeam, assets: partnerAssets, routing: bRouting as Record<string, string | undefined>, route: routeToggle(setBRouting), accent: 'partner' as const },
    { code: 'C', name: teamC, assets: teamCAssets, routing: cRouting as Record<string, string | undefined>, route: routeToggle(setCRouting), accent: 'third' as const },
  ];

  const threeTeamFlows = threeTeams.flatMap((from) =>
    threeTeams.filter((to) => to.code !== from.code).map((to) => ({
      from,
      to,
      items: [
        ...from.assets.players
          .filter((p) => from.routing[p.name] === to.code)
          .map((p) => ({ key: p.name, label: p.name, detail: formatMoney(p.salary) })),
        ...from.assets.picks
          .filter((pk) => from.routing[pk.key] === to.code)
          .map((pk) => ({ key: pk.key, label: pk.display_name, detail: '' })),
      ],
    }))
  ).filter((flow) => flow.items.length > 0);

  return (
    <div>
      {/* Top Header */}
      <div className="dash-header">
        <div>
          <h1 className="dash-title">Trade Center</h1>
          <span className="dash-subtitle">Build a deal, read the GM's answer, ask for a counter-offer.</span>
        </div>
        {!isTradeWindowOpen && (
          <div className="dash-badges">
            <span className="status-badge status-out">{tradeWindowMessage || `Trade window closed (${leagueState.replace('_', ' ')})`}</span>
          </div>
        )}
      </div>

      {leagueData?.user_role === 'only_coach' && (
        <div style={{
          background: 'linear-gradient(90deg, rgba(56, 189, 248, 0.1) 0%, rgba(20, 24, 36, 0.8) 100%)',
          border: '1px solid rgba(56, 189, 248, 0.3)',
          borderRadius: '12px',
          padding: '12px 18px',
          marginBottom: '20px',
          display: 'flex',
          alignItems: 'center',
          gap: '12px'
        }}>
          <Briefcase size={20} style={{ color: '#38bdf8', flexShrink: 0 }} />
          <div>
            <strong style={{ fontSize: '13px', color: '#f8fafc', display: 'block' }}>
              Head Coach Only Mode Active
            </strong>
            <span style={{ fontSize: '12px', color: '#94a3b8' }}>
              Trades and roster transactions are managed autonomously by the franchise General Manager. The GM operates at the Trade Deadline following the posture agreed during the Pre-Season Summit.
            </span>
          </div>
        </div>
      )}

      {/* Sub tabs */}
      <DashboardTabs
        idPrefix="trade"
        ariaLabel="Trade sections"
        active={activeSubTab}
        onChange={(id) => {
          setActiveSubTab(id as typeof activeSubTab);
          setError(null);
          setSuccessMessage(null);
        }}
        tabs={[
          { id: 'machine', label: 'Trade Machine' },
          { id: 'finder', label: 'Trade Finder' },
          { id: 'block', label: 'Trade Block' },
          { id: 'history', label: 'History' },
        ]}
      />

      {/* Alerts */}
      {successMessage && (
        <div className="card" style={{ borderColor: '#10b981', color: '#10b981', background: 'rgba(16,185,129,0.08)', padding: '12px 20px', marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Check size={18} /> {successMessage}
        </div>
      )}
      {error && (
        <div className="card" style={{ borderColor: '#ef4444', color: '#ef4444', background: 'rgba(239,68,68,0.08)', padding: '12px 20px', marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '10px' }}>
          <ShieldAlert size={18} /> {error}
        </div>
      )}

      <div role="tabpanel" id={`trade-panel-${activeSubTab}`} aria-labelledby={`trade-tab-${activeSubTab}`}>
      {!leagueData?.player_team_name && activeSubTab !== 'history' ? (
        <div className="card" style={{ padding: '40px', textAlign: 'center', background: 'rgba(255,184,0,0.02)', border: '1px solid rgba(255,184,0,0.15)', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '16px', margin: '20px 0' }}>
          <ShieldAlert size={48} style={{ color: 'var(--primary)' }} />
          <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 800 }}>Spectator Mode</h3>
          <p style={{ color: 'var(--text-secondary)', maxWidth: '500px', margin: 0, fontSize: '14px', lineHeight: '1.6' }}>
            In Spectator Mode, you can observe the simulation and view the Trade History log, but you cannot negotiate trades.
          </p>
        </div>
      ) : (
        <>
          {/* SUB-TAB 1: TRADE MACHINE (2-Team & 3-Team Blockbuster) */}
          {activeSubTab === 'machine' && (
            <div className="tm-root">
              {/* Partner strip */}
              <div className="tm-strip">
                <div className="tm-team">
                  <TeamCrest name={userTeamName} size={38} />
                  <div>
                    <span className="tm-team-label">You</span>
                    <span className="tm-team-name">{userTeamName}</span>
                  </div>
                </div>
                <span className="tm-swap" aria-hidden="true">⇄</span>
                {tradeMode === '2-team' ? (
                  renderTeamPicker('Trade partner', partnerTeam, '', (name) => {
                    setPartnerTeam(name);
                    fetchCustomTradeAssets(name);
                  })
                ) : (
                  <>
                    {renderTeamPicker('Partner B', partnerTeam, teamC, (name) => {
                      setPartnerTeam(name);
                      fetchCustomTradeAssets(name, teamC);
                    })}
                    <span className="tm-swap" aria-hidden="true">⇄</span>
                    {renderTeamPicker('Partner C', teamC, partnerTeam, (name) => {
                      setTeamC(name);
                      fetchCustomTradeAssets(partnerTeam, name);
                    })}
                  </>
                )}
                <div className="tm-modes" role="group" aria-label="Trade mode">
                  <button
                    type="button"
                    className={`tm-mode${tradeMode === '2-team' ? ' is-active' : ''}`}
                    aria-pressed={tradeMode === '2-team'}
                    onClick={() => {
                      setTradeMode('2-team');
                      setValidation3Team(null);
                    }}
                  >
                    2-team
                  </button>
                  <button
                    type="button"
                    className={`tm-mode${tradeMode === '3-team' ? ' is-active' : ''}`}
                    aria-pressed={tradeMode === '3-team'}
                    onClick={() => {
                      setTradeMode('3-team');
                      if (partnerTeam && teamC) {
                        fetchCustomTradeAssets(partnerTeam, teamC);
                      }
                    }}
                  >
                    3-team
                  </button>
                </div>
              </div>

              {/* 2-TEAM MODE */}
              {tradeMode === '2-team' && (
                partnerTeam ? (
                  <>
                    <div className="tm-grid">
                      <div className="tm-panel">
                        <div className="tm-panel-head">
                          <span className="tm-team-name">{userTeamName}</span>
                          <span className="tm-panel-count">Click a row to offer</span>
                        </div>
                        <TradeRosterTable
                          assets={userAssets}
                          accent="you"
                          selectedPlayers={selectedUserPlayers}
                          selectedPicks={selectedUserPicks}
                          onTogglePlayer={(name) => setSelectedUserPlayers((prev) => prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name])}
                          onTogglePick={(key) => setSelectedUserPicks((prev) => prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key])}
                        />
                      </div>
                      <div className="tm-panel">
                        <div className="tm-panel-head">
                          <span className="tm-team-name">{partnerTeam}</span>
                          <span className="tm-panel-count">Click a row to ask for</span>
                        </div>
                        <TradeRosterTable
                          assets={partnerAssets}
                          accent="partner"
                          selectedPlayers={selectedPartnerPlayers}
                          selectedPicks={selectedPartnerPicks}
                          onTogglePlayer={(name) => setSelectedPartnerPlayers((prev) => prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name])}
                          onTogglePick={(key) => setSelectedPartnerPicks((prev) => prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key])}
                        />
                      </div>
                    </div>

                    <div className="tm-dealtitle">The deal</div>
                    <div className="tm-deal">
                      <div className="tm-half tm-half-send">
                        <div className="tm-half-head"><span>You send</span><span>{formatMoney(totalOutgoingSalary)}</span></div>
                        {selectedUserPlayers.length + selectedUserPicks.length === 0 && (
                          <p className="tm-hint">Nothing yet. Click players or picks in your roster.</p>
                        )}
                        {selectedUserPlayers.map((name) => {
                          const p = userAssets.players.find((x) => x.name === name);
                          return renderChip(name, name, p ? formatMoney(p.salary) : '', () => setSelectedUserPlayers((prev) => prev.filter((n) => n !== name)));
                        })}
                        {selectedUserPicks.map((key) => {
                          const pick = userAssets.picks.find((x) => x.key === key);
                          return renderChip(key, pick?.display_name || key, '', () => setSelectedUserPicks((prev) => prev.filter((k) => k !== key)));
                        })}
                      </div>
                      <div className="tm-half tm-half-get">
                        <div className="tm-half-head"><span>You get</span><span>{formatMoney(totalIncomingSalary)}</span></div>
                        {selectedPartnerPlayers.length + selectedPartnerPicks.length === 0 && (
                          <p className="tm-hint">Nothing yet. Click players or picks in their roster.</p>
                        )}
                        {selectedPartnerPlayers.map((name) => {
                          const p = partnerAssets.players.find((x) => x.name === name);
                          return renderChip(name, name, p ? formatMoney(p.salary) : '', () => setSelectedPartnerPlayers((prev) => prev.filter((n) => n !== name)));
                        })}
                        {selectedPartnerPicks.map((key) => {
                          const pick = partnerAssets.picks.find((x) => x.key === key);
                          return renderChip(key, pick?.display_name || key, '', () => setSelectedPartnerPicks((prev) => prev.filter((k) => k !== key)));
                        })}
                      </div>
                    </div>

                    <div className="tm-verdict">
                      <div>
                        <div className="tm-figures">
                          <div className="tm-figure"><span>Out</span><b>{formatMoney(totalOutgoingSalary)}</b></div>
                          <div className="tm-figure"><span>In</span><b>{formatMoney(totalIncomingSalary)}</b></div>
                          <div className="tm-figure"><span>Net</span><b>{netLabel}</b></div>
                        </div>
                        <div className={`tm-rules ${validation ? (validation.is_valid ? 'is-ok' : 'is-bad') : 'is-idle'}`}>
                          {validation
                            ? (validation.is_valid ? <><Check size={16} /> CBA compliant</> : <><X size={16} /> CBA violation</>)
                            : 'Pick players or picks to check the CBA rules'}
                        </div>
                        {validation && <p className="tm-rules-msg">{validation.validation_message}</p>}
                      </div>

                      {validation?.is_valid ? (
                        <div className={`tm-gm ${validation.ai_accepted ? 'is-yes' : 'is-no'}`}>
                          <b>GM {partnerTeam}</b>
                          {validation.ai_accepted ? 'We accept the deal.' : validation.ai_reason}
                          {validation.ai_accepted && validation.why && <span className="tm-why">Why they'd do it: {validation.why}</span>}
                        </div>
                      ) : (
                        <div className="tm-gm">
                          <b>GM {partnerTeam}</b>
                          {validation ? 'Make the deal legal first and I will answer.' : 'Waiting for your offer.'}
                        </div>
                      )}

                      <div className="tm-actions">
                        <button
                          type="button"
                          className="tm-btn"
                          onClick={handleRequestCounterOffer}
                          disabled={counterLoading || !partnerTeam}
                        >
                          <MessageSquare size={16} />
                          {counterLoading ? 'Thinking...' : 'Ask for counter'}
                        </button>
                        <button
                          type="button"
                          className="tm-btn is-primary"
                          disabled={!validation?.is_valid || !validation?.ai_accepted || loading || !isTradeWindowOpen}
                          onClick={handleExecuteTrade}
                        >
                          Execute trade
                        </button>
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="tm-empty">Choose a trade partner to open the table.</div>
                )
              )}

              {/* 3-TEAM MODE */}
              {tradeMode === '3-team' && (
                partnerTeam && teamC ? (
                  <>
                    <div className="tm-teamtabs" role="tablist" aria-label="Franchise assets">
                      {threeTeams.map((t) => {
                        const routed = Object.values(t.routing).filter(Boolean).length;
                        return (
                          <button
                            key={t.code}
                            type="button"
                            role="tab"
                            aria-selected={threeTeamView === t.code}
                            className={`tm-teamtab${threeTeamView === t.code ? ' is-active' : ''}`}
                            onClick={() => setThreeTeamView(t.code as 'A' | 'B' | 'C')}
                          >
                            <TeamCrest name={t.name} size={28} />
                            {t.code === 'A' ? `${t.name} (You)` : t.name}
                            {routed > 0 && <b>{routed}</b>}
                          </button>
                        );
                      })}
                    </div>

                    {threeTeams.filter((t) => t.code === threeTeamView).map((t) => (
                      <div className="tm-panel" key={t.code}>
                        <div className="tm-panel-head">
                          <span className="tm-team-name">{t.name}</span>
                          <span className="tm-panel-count">Use the Send to buttons to route an asset</span>
                        </div>
                        <TradeRosterTable
                          assets={t.assets}
                          accent={t.accent}
                          routing={{
                            options: threeTeams
                              .filter((o) => o.code !== t.code)
                              .map((o) => ({ code: o.code, label: `→ ${crestLabel(o.name)}`, title: o.name })),
                            value: t.routing,
                            onRoute: t.route,
                          }}
                        />
                      </div>
                    ))}

                    <div className="tm-dealtitle">The deal</div>
                    {threeTeamFlows.length === 0 ? (
                      <div className="tm-half"><p className="tm-hint">Nothing routed yet. Pick a franchise above and send its players or picks to another team.</p></div>
                    ) : (
                      <div className="tm-flows">
                        {threeTeamFlows.map((flow) => (
                          <div className="tm-flow" key={`${flow.from.code}${flow.to.code}`}>
                            <div className="tm-flow-head">{flow.from.name}<span>→</span>{flow.to.name}</div>
                            {flow.items.map((item) => renderChip(item.key, item.label, item.detail, () => flow.from.route(item.key, flow.to.code)))}
                          </div>
                        ))}
                      </div>
                    )}

                    <div className="tm-verdict">
                      <div>
                        <div className={`tm-rules ${validation3Team ? (validation3Team.is_valid ? 'is-ok' : 'is-bad') : 'is-idle'}`}>
                          {validation3Team
                            ? (validation3Team.is_valid ? <><Check size={16} /> CBA compliant for all three teams</> : <><X size={16} /> CBA violation</>)
                            : 'Route assets to check the CBA rules'}
                        </div>
                        {validation3Team && !validation3Team.is_valid && <p className="tm-rules-msg">{validation3Team.validation_message}</p>}
                      </div>

                      <div>
                        {[{ team: partnerTeam, res: validation3Team?.team_b }, { team: teamC, res: validation3Team?.team_c }].map(({ team, res }) => (
                          <div key={team} className={`tm-gm${res ? (res.accepted ? ' is-yes' : ' is-no') : ''}`}>
                            <b>GM {team}</b>
                            {res ? (res.accepted ? 'We accept the deal.' : res.reason) : 'Waiting for the offer.'}
                          </div>
                        ))}
                      </div>

                      <div className="tm-actions">
                        <button
                          type="button"
                          className="tm-btn is-primary"
                          disabled={!validation3Team?.all_accepted || loading || !isTradeWindowOpen}
                          onClick={handleExecute3TeamTrade}
                        >
                          Execute 3-way trade
                        </button>
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="tm-empty">Choose both partner teams (B and C) to open the 3-team table.</div>
                )
              )}
            </div>
          )}

          {/* SUB-TAB 2: TRADE FINDER (boarding passes) */}
          {activeSubTab === 'finder' && (
            <TradeFinderPanel
              userTeam={userTeamName}
              players={tradeablePlayers}
              picks={tradeablePicks}
              selectedPlayers={finderSelectedPlayers}
              selectedPicks={finderSelectedPicks}
              onTogglePlayer={(name) => setFinderSelectedPlayers((prev) => prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name])}
              onTogglePick={(key) => setFinderSelectedPicks((prev) => prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key])}
              onClear={() => {
                setFinderSelectedPlayers([]);
                setFinderSelectedPicks([]);
                setFinderOffers([]);
              }}
              onFind={handleSearchFinderTrades}
              onOpenAskingPrice={() => setShowWhatWouldItTakeModal(true)}
              loading={loading}
              targetRole={targetNeedRole}
              onTargetRole={setTargetNeedRole}
              minOvr={minNeedOvr}
              onMinOvr={setMinNeedOvr}
              onSearchByNeed={handleSearchByNeed}
              needLoading={needSearchLoading}
              offers={finderOffers}
              filter={finderFilterMode}
              onFilter={setFinderFilterMode}
              onAccept={(offer) => {
                if (offer.trade_type === '3-team') handleAccept3TeamFinderOffer(offer);
                else if (offer.trade_type === 'multi-team') handleAccept4TeamFinderOffer(offer);
                else handleAcceptFinderOffer(offer);
              }}
              onOpen={(offer) => {
                if (offer.trade_type === '3-team') handleLoad3TeamIntoMachine(offer);
                else handleLoadOfferIntoMachine(offer);
              }}
            />
          )}

          {/* SUB-TAB 3: TRADE BLOCK (offer sheets) */}
          {activeSubTab === 'block' && (
            <TradeBlockPanel
              roster={(leagueData?.league_database?.players_active || []).filter((p) => p.squadra === userTeamName)}
              offers={blockOffers}
              loading={blockLoading}
              onToggle={handleToggleTradeBlock}
              onGenerate={handleGenerateBlockOffers}
              onRespond={handleRespondBlockOffer}
            />
          )}

          {/* SUB-TAB 4: HISTORY */}
          {activeSubTab === 'history' && (
            <TradeHistoryLog
              initialRawTrades={[
                ...(leagueData?.offseason?.scambi_midseason || []),
                ...(leagueData?.offseason?.scambi || [])
              ]}
              currentTeamName={leagueData?.player_team_name}
              currentSeason={leagueData?.stagione}
            />
          )}
        </>
      )}
      </div>

      {/* REBUTTAL / COUNTER-OFFER MODAL */}
      {showCounterModal && counterOffer && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(5px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: '20px' }}>
          <div className="card" style={{ width: '540px', maxWidth: '90%', padding: '24px', borderRadius: '14px', border: '1px solid var(--primary-trans)', boxShadow: '0 10px 40px rgba(0,0,0,0.8)' }}>
            
            <div className="flex-between" style={{ borderBottom: '1px solid var(--border)', paddingBottom: '12px', marginBottom: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <MessageSquare size={20} style={{ color: 'var(--primary)' }} />
                <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 800 }}>Counter-Offer from {partnerTeam} GM</h3>
              </div>
              <button onClick={() => setShowCounterModal(false)} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}>
                <X size={20} />
              </button>
            </div>

            <div style={{ background: 'rgba(255,255,255,0.02)', padding: '16px', borderRadius: '10px', border: '1px solid var(--border)', marginBottom: '20px', fontSize: '14px', lineHeight: '1.6' }}>
              {counterOffer.message}
              {counterOffer.why && <div style={{ marginTop: '6px', fontSize: '12px', color: 'var(--text-muted)' }}>Why they'd do it: {counterOffer.why}</div>}
            </div>

            {counterOffer.has_counter && !counterOffer.accepted_as_is && (
              <div style={{ marginBottom: '20px' }}>
                <div style={{ fontSize: '12px', textTransform: 'uppercase', color: 'var(--primary)', fontWeight: 800, marginBottom: '8px' }}>
                  Requested Modifications:
                </div>
                <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '13px' }}>
                  {counterOffer.add_user_players.map((pName, idx) => (
                    <li key={idx} style={{ padding: '8px 12px', background: 'rgba(212,175,55,0.1)', border: '1px solid rgba(212,175,55,0.25)', borderRadius: '6px', color: 'var(--text-primary)' }}>
                      ⛹️‍♂️ Add Player: <strong>{pName}</strong>
                    </li>
                  ))}
                  {counterOffer.add_user_picks.map((pk, idx) => (
                    <li key={idx} style={{ padding: '8px 12px', background: 'rgba(212,175,55,0.1)', border: '1px solid rgba(212,175,55,0.25)', borderRadius: '6px', color: 'var(--text-primary)' }}>
                      🎫 Add Draft Pick: <strong>{pk.replace(':', ' ').replace('R1', '1st Round').replace('R2', '2nd Round')}</strong>
                    </li>
                  ))}
                  {Object.entries(counterOffer.modified_protections || {}).map(([pk, prot], idx) => (
                    <li key={idx} style={{ padding: '8px 12px', background: 'rgba(212,175,55,0.1)', border: '1px solid rgba(212,175,55,0.25)', borderRadius: '6px', color: 'var(--text-primary)' }}>
                      🛡️ Change Protection on {pk}: <strong>{prot}</strong>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="flex-between" style={{ borderTop: '1px solid var(--border)', paddingTop: '16px' }}>
              <button className="btn btn-secondary" onClick={() => setShowCounterModal(false)} style={{ padding: '8px 16px' }}>
                Close
              </button>
              {counterOffer.has_counter && !counterOffer.accepted_as_is && (
                <button className="btn btn-primary" onClick={handleApplyCounterOffer} style={{ padding: '10px 20px', fontWeight: 800 }}>
                  Accept & Apply Counter-Offer
                </button>
              )}
            </div>

          </div>
        </div>
      )}

      {/* WHAT WOULD IT TAKE MODAL */}
      {showWhatWouldItTakeModal && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.8)', backdropFilter: 'blur(6px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: '20px' }}>
          <div className="card" style={{ width: '640px', maxWidth: '95%', padding: '24px', borderRadius: '16px', border: '1px solid var(--primary)', boxShadow: '0 15px 50px rgba(0,0,0,0.8)', background: '#11151f' }}>
            <div className="flex-between" style={{ borderBottom: '1px solid var(--border)', paddingBottom: '14px', marginBottom: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <DollarSign size={20} className="logo-gold" />
                <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 800 }}>Asking Price Calculator</h3>
              </div>
              <button onClick={() => { setShowWhatWouldItTakeModal(false); setWhatWouldItTakeResult(null); }} style={{ background: 'transparent', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }}><X size={20} /></button>
            </div>
            <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '16px' }}>
              Select any player across the NBA to find out in real time if their team is willing to trade them and what minimum package of assets is required.
            </p>
            <div style={{ display: 'flex', gap: '10px', marginBottom: '16px' }}>
              <select
                value={whatWouldItTakeTarget}
                onChange={(e) => { setWhatWouldItTakeTarget(e.target.value); setWhatWouldItTakeResult(null); }}
                style={{ flex: 1, background: 'var(--bg-app)', color: 'var(--text-primary)', border: '1px solid var(--border)', borderRadius: '8px', padding: '10px 12px', fontSize: '13px' }}
              >
                <option value="">-- Select an opposing player --</option>
                {leagueData?.league_database?.players_active
                  ?.filter(p => p.squadra !== leagueData.player_team_name)
                  ?.slice()
                  ?.sort((a, b) => b.ovr - a.ovr)
                  ?.map(p => (
                    <option key={p.id} value={p.nome}>
                      {p.nome} ({formatPosition(p.ruolo)}, {p.ovr} OVR) - {p.squadra} [${(((p as any).salario || (p as any).stipendio || 0) as number).toFixed(1)}M]
                    </option>
                  ))}
              </select>
              <button
                className="btn btn-primary"
                onClick={() => handleCalculateWhatWouldItTake(whatWouldItTakeTarget)}
                disabled={!whatWouldItTakeTarget || whatWouldItTakeLoading}
                style={{ padding: '8px 18px', fontWeight: 700, fontSize: '13px', whiteSpace: 'nowrap' }}
              >
                {whatWouldItTakeLoading ? 'GM Evaluating...' : 'Ask GM'}
              </button>
            </div>

            {whatWouldItTakeResult && (
              <div style={{ marginTop: '16px' }}>
                {!whatWouldItTakeResult.attainable ? (
                  <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', padding: '14px', borderRadius: '8px', color: '#f87171' }}>
                    <div style={{ fontWeight: 800, fontSize: '14px', marginBottom: '4px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <ShieldAlert size={16} /> {String(whatWouldItTakeResult.reason || '').startsWith('Untouchable') ? 'Untouchable Cornerstone' : 'No deal'}
                    </div>
                    <div style={{ fontSize: '13px' }}>{whatWouldItTakeResult.reason}</div>
                  </div>
                ) : (
                  <div style={{ background: 'rgba(52,211,153,0.08)', border: '1px solid rgba(52,211,153,0.3)', padding: '16px', borderRadius: '8px' }}>
                    <div style={{ fontWeight: 800, color: '#34d399', fontSize: '14px', marginBottom: '6px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <Check size={16} /> Deal Possible!
                    </div>
                    <div style={{ fontSize: '13px', color: 'var(--text-primary)', marginBottom: '12px' }}>
                      {whatWouldItTakeResult.message}
                    </div>
                    {whatWouldItTakeResult.why && (
                      <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '12px' }}>Why they'd do it: {whatWouldItTakeResult.why}</div>
                    )}
                    <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '6px' }}>
                      Required assets from your roster:
                    </div>
                    <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                      {whatWouldItTakeResult.players_needed?.map((pn: string, i: number) => (
                        <span key={i} style={{ fontSize: '12px', background: 'rgba(239,68,68,0.15)', color: '#f87171', border: '1px solid rgba(239,68,68,0.3)', padding: '4px 10px', borderRadius: '6px', fontWeight: 600 }}>
                          ⛹️‍♂️ {pn}
                        </span>
                      ))}
                      {whatWouldItTakeResult.picks_needed?.map((pkn: string, i: number) => (
                        <span key={i} style={{ fontSize: '12px', background: 'rgba(96,165,250,0.15)', color: '#60a5fa', border: '1px solid rgba(96,165,250,0.3)', padding: '4px 10px', borderRadius: '6px', fontWeight: 600 }}>
                          🎫 Pick {pkn}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '20px', borderTop: '1px solid var(--border)', paddingTop: '14px' }}>
              <button className="btn btn-secondary" onClick={() => { setShowWhatWouldItTakeModal(false); setWhatWouldItTakeResult(null); }}>
                Close
              </button>
            </div>

          </div>
        </div>
      )}

    </div>
  );
};
