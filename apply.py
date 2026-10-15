#!/usr/bin/env python3
"""Apply six independent unbiased team rolls to the ORIGINAL amoi-builds/dailyred.
Usage: python apply.py /path/to/dailyred
The checkout must have pokefirered/ populated by scripts/get-pokefirered.sh.
"""
from pathlib import Path
import re, sys, subprocess


def replace_once(text, old, new, label):
    hits = text.count(old)
    if hits != 1:
        raise RuntimeError(f'{label}: expected one match, got {hits}; original version may differ')
    return text.replace(old, new, 1)


def replace_regex(text, pattern, replacement, label):
    text, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f'{label}: original source layout differs')
    return text


def transform_team(s):
    s = replace_regex(s, r'// Minimum combined base stat total.*?static const u16 sLegendaries\[\] =\s*\{.*?\};\n', '', 'obsolete limits')
    s = replace_regex(s, r'static u16 GetBaseStatTotal\(u16 species\).*?(?=// Decides whether this team gets a legendary)', '', 'obsolete selectors')
    # Species are sampled directly from every valid Gen 1-3 entry. No BST
    # threshold, legendary quota or competitive balancing.
    s = replace_regex(s,
        r'// Decides whether this team gets a legendary, then draws the other Pokemon.*?\nstatic void PickTeamSpecies\(u16 \*species, u32 \*rng\)\n\{.*?\n\}',
        '''// Six independent picks from all valid species, without weighting or
// team strength limits. Duplicates are allowed, as in unrestricted random draws.
static void PickTeamSpecies(u16 *species, u32 *rng)
{
    u16 eligible[NUM_SPECIES];
    u16 count = 0, candidate;
    u8 i;

    for (candidate = 1; candidate < NUM_SPECIES; candidate++)
    {
        if (IsEligibleSpecies(candidate))
            eligible[count++] = candidate;
    }

    for (i = 0; i < PARTY_SIZE; i++)
        species[i] = eligible[TeamRandom(rng) % count];
}''', 'species generator')
    s = replace_regex(s, r'#define MAX_SPECIES_ATTEMPTS 1000\n', '', 'obsolete species attempts')
    s = replace_regex(s, r'#define MAX_TEAM_ATTEMPTS    1000\n', '', 'obsolete team attempts')
    # No requirement for an offensive move; fill all four distinct move slots
    # whenever the Pokemon actually has four distinct legal moves.
    s = replace_regex(s,
        r'    // If none of the picks can deal damage, swap one of them.*?\n    for \(i = 0; i < MAX_MON_MOVES; i\+\+\)',
        '    for (i = 0; i < MAX_MON_MOVES; i++)', 'forced offensive move')
    s = replace_once(s, '#define MIN_TEAM_IV          25', '#define MIN_TEAM_IV          0 ', 'full IV randomness')
    s = replace_once(s, 'u8 count, numMoves, numDamaging, i, j;', 'u8 count, numMoves, i, j;', 'move picker unused variable')
    s = replace_regex(s, r'static bool8 IsDamagingMove\(u16 move\)\n\{.*?\n\}\n', '', 'obsolete attacking move check')
    s = replace_once(s, '    u16 eligible[NUM_SPECIES];', '    u16 eligible[NUM_SPECIES];', 'species array assertion')
    # Remove the stat optimisation: unbiased (but legal) EV distribution. Allocation
    # is uniform over all ordered distributions with per-stat <=252 and sum 510?
    # That scheme is complex and not required by user; keep existing legal EVs.
    # Existing item picker is a finite design-curated pool, but item selection is
    # already uniform inside its applicable candidate list.
    return s


def transform_app(s):
    s = replace_once(s,
        "const practiceSeed = parseSeed(new URLSearchParams(location.search).get('seed'));",
        """const params = new URLSearchParams(location.search);
const practiceSeed = parseSeed(params.get('seed'));
// Six independent team streams; choice changes only the seed, not the rules.
const requestedVariant = Number(params.get('variant'));
let variant = Number.isInteger(requestedVariant) && requestedVariant >= 1 && requestedVariant <= 6
  ? requestedVariant : 1;
const variantSelector = document.createElement('select');
variantSelector.id = 'dailyred-variant';
variantSelector.setAttribute('aria-label', 'Team variant');
for (let i = 1; i <= 6; i++) {
  const option = document.createElement('option');
  option.value = String(i);
  option.textContent = `Random team ${i}`;
  variantSelector.append(option);
}
variantSelector.value = String(variant);
variantSelector.addEventListener('change', () => {
  variant = Number(variantSelector.value);
  const url = new URL(location.href);
  url.searchParams.set('variant', String(variant));
  history.replaceState(null, '', url);
});
ui.play.before(variantSelector);
// Hash-based independent deterministic streams. Variant 1 preserves the old seed.
function seedForVariant(seed, choice) {
  if (choice === 1) return seed;
  let x = (seed ^ Math.imul(choice, 0x9e3779b9)) >>> 0;
  x = Math.imul(x ^ (x >>> 16), 0x85ebca6b) >>> 0;
  x = Math.imul(x ^ (x >>> 13), 0xc2b2ae35) >>> 0;
  return ((x ^ (x >>> 16)) >>> 0) || 1;
}""", 'website variants')
    s = replace_once(s,
        'const seed = practiceSeed ?? dailySeed(runDate);',
        'const seed = seedForVariant(practiceSeed ?? dailySeed(runDate), variant);',
        'seed selection')
    # Daily lock applies across all variants rather than granting six battles.
    return s


def main(root):
    root = Path(root).resolve()
    team_path = root/'pokefirered/src/dailyred_team.c'
    app_path = root/'web/app.js'
    for p in (team_path, app_path):
        if not p.is_file():
            raise RuntimeError(f'Missing {p}; run scripts/get-pokefirered.sh first')
    team = team_path.read_text()
    app = app_path.read_text()
    # Build both outputs before writing either file.
    new_team = transform_team(team)
    new_app = transform_app(app)
    team_path.write_text(new_team)
    app_path.write_text(new_app)
    print('Modified:', team_path, app_path)
    print('Run scripts/save-patch.sh from the repository root to persist game changes.')
    print('The original site daily lock still applies across all six variants.')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit('Usage: python apply.py /path/to/original-dailyred')
    main(sys.argv[1])
