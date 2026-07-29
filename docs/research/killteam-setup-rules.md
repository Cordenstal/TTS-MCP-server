# Kill Team setup research

Date checked: 2026-07-28

## Findings

- The official Kill Team Lite Rules describe setup as: determine initiative,
  select drop zones, then starting with the player who has initiative, players
  alternate setting up one third of their kill team, rounded up. Each operative
  must be wholly within its drop zone and receives a Conceal order.
- A roster or container of possible operatives is not automatically the team
  that enters the battle. Faction rules define the legal composition of the
  selected kill team, including required leader/specialist choices, duplicate
  limits, and faction-specific caps.
- The Legionaries faction rules currently describe one leader choice plus five
  operatives chosen from the permitted list, with non-Warrior operative
  uniqueness restrictions.
- The Novitiates faction rules currently describe one Superior plus nine
  operatives chosen from the permitted list, with uniqueness restrictions and a
  cap of two Purgatus operatives.

## Design consequence

The TTS roster container should represent the available candidate pool. Before
placement, the runtime needs a selected-battle-team state for each side. That
state must distinguish eligible-but-unused candidates from selected-and-placed
operatives. It must also validate faction composition before deployment begins.

The repository's proposed one-model-at-a-time alternation is therefore a
variant of the official Lite setup sequence unless the selected mission or
rules pack specifies otherwise. The implementation should make the placement
cadence configurable or explicitly name the chosen variant rather than encode
one cadence as universal Kill Team law.

## Primary sources

- [Games Workshop Kill Team Lite Rules (PDF)](https://assets.warhammer-community.com/rules-downloads/kill-team/key-downloads/kill-team-lite-rules/killteam_keydownloads_literules_eng_02.10.24.pdf)
- [Games Workshop Kill Team downloads and updates](https://www.warhammer-community.com/en-gb/downloads/kill-team/)
- [Games Workshop Legionaries team rules](https://assets.warhammer-community.com/eng_kt_teamrules_legionaries_jan25-kf5yeock1w-lsotyrx2w0.pdf)
- [Games Workshop Novitiates team rules](https://assets.warhammer-community.com/eng_kt_teamrules_novitiates_jan25-tnp5mw2dpk-9utbrqfroc.pdf)
