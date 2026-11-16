import React, { useState } from 'react';
import { crestHue, crestLabel } from '../../utils/crest';
import { normalizeRole } from '../../utils/roles';
import type { TradeOffer } from './types';

interface BoardingPassProps {
  offer: TradeOffer;
  userTeam: string;
  onAccept: () => void;
  /** Not offered for multi-team chains: the Trade Machine only handles 2 and 3 teams. */
  onOpen?: () => void;
}

const STATUS: Record<string, { label: string; tone: 'ok' | 'mid' | 'low'; level: number }> = {
  High: { label: 'Cleared', tone: 'ok', level: 4 },
  Medium: { label: 'Delayed', tone: 'mid', level: 3 },
  Low: { label: 'Unlikely', tone: 'low', level: 1 },
};

const money = (millions: number): string => `$${millions.toFixed(1)}M`;
const totalSalary = (list?: any[]): number => (list || []).reduce((sum, p) => sum + (p.salary || 0), 0);

const TeamCode: React.FC<{ name: string; caption?: string; small?: boolean; align?: 'left' | 'right' | 'center' }> = ({ name, caption, small, align = 'left' }) => (
  <div className="bp-team" style={{ textAlign: align }}>
    <div className={`bp-code${small ? ' is-small' : ''}`} style={{ color: `hsl(${crestHue(name)} 72% 66%)` }} title={name}>{crestLabel(name)}</div>
    <div className="bp-city">{caption ?? name}</div>
  </div>
);

const Path: React.FC<{ glyph?: string }> = ({ glyph = '›' }) => (
  <div className="bp-path" aria-hidden="true"><i /><b>{glyph}</b><i /></div>
);

const AssetList: React.FC<{ players?: any[]; picks?: string[] }> = ({ players = [], picks = [] }) => (
  <>
    {players.map((p, i) => {
      const role = p.position || p.role;
      return (
        <div key={`${p.name}-${i}`}>
          {p.name} <small>{role ? `${normalizeRole(role)} · ` : ''}{p.ovr}</small>
        </div>
      );
    })}
    {picks.map((pk, i) => <div key={`${pk}-${i}`}>{pk} <small>pick</small></div>)}
    {players.length + picks.length === 0 && <div><small>Nothing</small></div>}
  </>
);

export const BoardingPass: React.FC<BoardingPassProps> = ({ offer, userTeam, onAccept, onOpen }) => {
  const [showRoute, setShowRoute] = useState(false);
  const kind = offer.trade_type === '3-team' ? 'connecting' : offer.trade_type === 'multi-team' ? 'chain' : 'direct';
  const status = offer.likelihood ? STATUS[offer.likelihood] : undefined;

  let heading = 'Direct · 2 teams';
  let route: React.ReactNode;
  let fields: React.ReactNode;
  let note: string | undefined;

  if (kind === 'direct') {
    note = offer.partner_strategy ? `Posture: ${offer.partner_strategy}` : undefined;
    route = (
      <>
        <TeamCode name={userTeam} caption="You" />
        <Path glyph="⇄" />
        <TeamCode name={offer.partner_team} align="right" />
      </>
    );
    fields = (
      <>
        <div className="bp-field"><span>You send</span><AssetList players={offer.giving_players} picks={offer.giving_picks} /></div>
        <div className="bp-field"><span>You get</span><AssetList players={offer.receiving_players} picks={offer.receiving_picks} /></div>
        <div className="bp-field"><span>Fare (salary)</span><div>{money(totalSalary(offer.giving_players))} out</div><div>{money(totalSalary(offer.receiving_players))} in</div></div>
      </>
    );
  } else if (kind === 'connecting') {
    heading = 'Connecting · 3 teams';
    note = offer.fit_description;
    route = (
      <>
        <TeamCode name={userTeam} caption="You" />
        <Path />
        <TeamCode name={offer.partner_team} caption="Stop" small align="center" />
        <Path />
        <TeamCode name={offer.third_team || '?'} caption="Stop" small align="center" />
        <Path />
        <TeamCode name={userTeam} caption="Back to you" align="right" />
      </>
    );
    fields = (
      <>
        <div className="bp-field"><span>You → {crestLabel(offer.partner_team)}</span><AssetList players={offer.user_gives_to_b} picks={offer.giving_picks} /></div>
        <div className="bp-field"><span>{crestLabel(offer.partner_team)} → {crestLabel(offer.third_team || '?')}</span><AssetList players={offer.team_c_receives} /></div>
        <div className="bp-field"><span>{crestLabel(offer.third_team || '?')} → You</span><AssetList players={offer.user_receives} picks={offer.receiving_picks} /></div>
      </>
    );
  } else {
    const teams = offer.teams || [];
    heading = `Itinerary · ${teams.length || offer.chain_length || '?'} teams`;
    const mine = (offer.flow || []).filter((f) => f.to === userTeam);
    route = (
      <>
        {teams.map((team, i) => (
          <React.Fragment key={`${team}-${i}`}>
            {i > 0 && <Path />}
            <TeamCode name={team} caption={team === userTeam ? 'You' : 'Stop'} small />
          </React.Fragment>
        ))}
      </>
    );
    fields = (
      <>
        <div className="bp-field"><span>You end up with</span>
          {mine.length > 0 ? mine.map((f, i) => <div key={i}>{f.player} <small>{f.role} · {f.ovr}</small></div>) : <div><small>See the full route</small></div>}
        </div>
        <div className="bp-field"><span>Players moving</span><div>{offer.flow?.length ?? 0} across {teams.length} teams</div></div>
        {offer.summary && <div className="bp-field bp-summary"><span>Summary</span><div>{offer.summary}</div></div>}
        {showRoute && (
          <div className="bp-legs">
            {(offer.flow || []).map((f, i) => (
              <div key={i} className="bp-leg">
                <span>{crestLabel(f.from)} → {crestLabel(f.to)}</span>
                <b>{f.player}</b>
                <small>{f.role} · {f.ovr} · {money(f.salary || 0)}</small>
              </div>
            ))}
          </div>
        )}
      </>
    );
  }

  return (
    <article className={`bp bp-${kind}`}>
      <div className="bp-main">
        <div className="bp-top"><span>Trade pass</span><span>{heading}</span></div>
        <div className="bp-route">{route}</div>
        <div className="bp-fields">{fields}</div>
        {offer.why && <div className="bp-note bp-why">Why they'd do it: {offer.why}</div>}
      </div>
      <div className="bp-stub">
        <div>
          <span className="bp-cap">Boarding</span>
          <div className={`bp-status is-${status?.tone ?? 'idle'}`}>{status?.label ?? 'Proposed'}</div>
          {status && (
            <div className={`bp-meter is-${status.tone}`} aria-hidden="true">
              {[0, 1, 2, 3, 4].map((i) => <i key={i} className={i < status.level ? 'on' : ''} />)}
            </div>
          )}
          {note && <div className="bp-note is-quote" title={note}>{note}</div>}
        </div>
        <div className="bp-actions">
          <div className="bp-barcode" aria-hidden="true" />
          <button type="button" className="bp-btn is-primary" onClick={onAccept}>{kind === 'chain' ? 'Accept chain' : 'Accept'}</button>
          {kind === 'chain' ? (
            <button type="button" className="bp-btn" onClick={() => setShowRoute((v) => !v)} aria-expanded={showRoute}>
              {showRoute ? 'Hide route' : 'Full route'}
            </button>
          ) : (
            onOpen && <button type="button" className="bp-btn" onClick={onOpen}>Open in machine</button>
          )}
        </div>
      </div>
    </article>
  );
};
