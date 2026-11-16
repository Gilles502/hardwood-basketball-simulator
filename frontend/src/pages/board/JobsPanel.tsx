// "GM market & jobs" tab: the user's own job market (franchise offers, resignation) above the GM market.
import React from 'react';
import { useLeagueStore } from '../../store/leagueStore';
import { FranchiseCarouselModal } from '../../components/FranchiseCarouselModal';
import { GMMarket } from './GMMarket';
import './Office.css';

export const JobsPanel: React.FC = () => {
  // A GM without a team (fired or resigned) has no player_team_name and is_spectator is set, but still needs the
  // offers; only a save started as a spectator has no GM career to look for a job with.
  const teamName = useLeagueStore((s) => s.leagueData?.player_team_name || 'Free Agent GM');
  const showJobs = useLeagueStore((s) => !!s.leagueData && s.leagueData.user_role !== 'spectator');

  return (
    <div className="of-root">
      {showJobs && (
        <section className="of-section" aria-labelledby="of-jobs-head">
          <h2 className="of-section-head" id="of-jobs-head">Your job market <span>·</span> offers</h2>
          <FranchiseCarouselModal
            currentTeamName={teamName}
            onSwitchedTeam={() => window.location.reload()}
          />
        </section>
      )}
      <section className="of-section" aria-labelledby="of-market-head">
        <h2 className="of-section-head" id="of-market-head">GM market <span>·</span> unemployed GMs</h2>
        <GMMarket />
      </section>
    </div>
  );
};
