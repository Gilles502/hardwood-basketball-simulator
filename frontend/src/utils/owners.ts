// Owner personalities are stored with their Italian ids (CONFIG.ECONOMY.OWNER_TYPES); show them in English.
const OWNER_LABELS: Record<string, string> = {
  Spendaccione: 'Big spender',
  Esigente: 'Demanding',
  Bilanciato: 'Balanced',
  Equilibrato: 'Balanced',
  Ricostruttore: 'Rebuilder',
  Risparmiatore: 'Penny-pincher',
};

export function ownerLabel(personality: string | null | undefined): string {
  if (!personality) return 'Unknown';
  return OWNER_LABELS[personality] ?? personality;
}
