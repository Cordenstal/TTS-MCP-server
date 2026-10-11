# Plague Marines team rules research

Date checked: 2026-10-11

Question (issue #3): what do the current Kill Team Plague Marines team rules
give a tactical AI to work with, and what does this team need a **team
profile** schema to represent?

This page summarizes the official rules. It does not reproduce card text. Where
a rule's exact wording matters for adjudication, read the source PDF.

## Sources and version

| Source | Version / date | Used for |
| --- | --- | --- |
| [Plague Marines team rules (PDF)][pm] | Warhammer Community download entry created 06/11/2024, last updated 26/08/2026. The PDF's update log has an errata and rules commentary dated **August '26** | Datacards, faction rules, ploys, faction equipment, selection, update log |
| [Kill Team Lite Rules (PDF)][lite] | Jul '25 edition (download entry dated 23/07/2025) | Ploy cost, CP economy, injured rule, common weapon-rule definitions |
| [Universal Equipment (PDF)][ue] | Download entry dated 17/06/2026 | Krak and frag grenade profiles used by the Bombardier |
| [Core Rules: Update Log (PDF)][crul] | Download entry dated 17/06/2026 | Rulings that name Plague Marine rules |
| [Approved Ops 2025 Tournament Companion (PDF)][aotc] | Download entry dated 26/08/2026 | Rotation status |

I found the PDF URLs through the Warhammer Community downloads search API (the
endpoint behind <https://www.warhammer-community.com/en-gb/downloads/kill-team/>).
The team-rules PDF is 11 pages: datacards, the selection and faction-rule card,
ploys, equipment, the update log, then lore and loadout pages.

## Kill team selection

- **Archetypes:** Security, Seek & Destroy. Mission packs such as Approved Ops
  use archetypes. The team rules do not.
- **Composition:** 1 Plague Marine Champion (the leader), plus 5 operatives
  chosen from Bombardier, Fighter, Heavy Gunner, Icon Bearer, Malignant
  Plaguecaster and Warrior.
- **Uniqueness:** each operative on that list can be taken at most once. Five
  picks from six options means a legal team is always the Champion plus all
  but one of the six specialists, so a roster has exactly 6 operatives.
- **Loadouts:** no operative has weapon options. Each one carries every weapon
  on its datacard. The loadout pages show the same weapons.
- **Rotation:** Plague Marines are in the Volkus season block of the Approved
  Ops 2025 Classified rotation ([AOTC][aotc]).

## Operative datacards

Every operative has APL 3, Move 5", Save 3+ and a `32` printed in the card
corner. Every operative also carries the keywords PLAGUE MARINE, CHAOS and
HERETIC ASTARTES. The `32` is read here as a 32 mm base size (see
uncertainties).

| Operative | APL | Move | Save | Wounds | Extra keywords | Role notes |
| --- | --- | --- | --- | --- | --- | --- |
| Champion | 3 | 5" | 3+ | **15** | LEADER, CHAMPION | Mandatory leader. Heals itself from poisoned enemies' wound loss |
| Bombardier | 3 | 5" | 3+ | 14 | BOMBARDIER | Grenadier |
| Fighter | 3 | 5" | 3+ | 14 | FIGHTER | Melee and area damage (Flail) |
| Heavy Gunner | 3 | 5" | 3+ | 14 | HEAVY GUNNER | Short-range Torrent flamer-type weapon |
| Icon Bearer | 3 | 5" | 3+ | 14 | ICON BEARER | Objective control, aura for the Contagion ploy |
| Malignant Plaguecaster | 3 | 5" | 3+ | 14 | PSYKER | Psychic attacks, poison application, healing |
| Warrior | 3 | 5" | 3+ | 14 | WARRIOR | Durable line operative with a boltgun |

### Weapons

Hit is shown as the target number. Damage is shown as normal/critical. In this
table, "Poison" and "Toxic" are the team's own asterisked rules (see faction
rules).

| Operative | Weapon | Type | ATK | HIT | DMG | Weapon rules |
| --- | --- | --- | --- | --- | --- | --- |
| Champion | Plasma pistol (standard) | Ranged | 4 | 3+ | 3/5 | Range 8", Piercing 1 |
| Champion | Plasma pistol (supercharge) | Ranged | 4 | 3+ | 4/5 | Range 8", Hot, Lethal 5+, Piercing 1 |
| Champion | Plague sword | Melee | 5 | 3+ | 4/5 | Severe, Poison, Toxic |
| Bombardier | Boltgun | Ranged | 4 | 3+ | 3/4 | none |
| Bombardier | Fists | Melee | 4 | 3+ | 3/4 | none |
| Fighter | Bolt pistol | Ranged | 4 | 3+ | 3/4 | Range 8" |
| Fighter | Flail of Corruption | Melee | 5 | 3+ | 4/5 | Brutal, Severe, Shock, Poison |
| Heavy Gunner | Bolt pistol | Ranged | 4 | 3+ | 3/4 | Range 8" |
| Heavy Gunner | Plague spewer | Ranged | 5 | **2+** | 3/3 | Range 7", Saturate, Severe, Torrent 2", Poison |
| Heavy Gunner | Fists | Melee | 4 | 3+ | 3/4 | none |
| Icon Bearer | Bolt pistol | Ranged | 4 | 3+ | 3/4 | Range 8" |
| Icon Bearer | Plague knife | Melee | 5 | 3+ | 3/4 | Severe, Poison |
| Plaguecaster | Entropy | Ranged | 4 | 3+ | 3/7 | PSYCHIC, Range 7", Saturate, Severe, Poison |
| Plaguecaster | Plague wind | Ranged | 6 | 3+ | 2/3 | PSYCHIC, Saturate, Severe, Torrent 1", Poison (no Range rule printed) |
| Plaguecaster | Corrupted staff | Melee | 4 | 3+ | 3/4 | PSYCHIC, Severe, Shock, Stun, Poison |
| Warrior | Boltgun | Ranged | 4 | 3+ | 3/4 | Toxic |
| Warrior | Plague knife | Melee | 4 | 3+ | 3/4 | Severe, Poison |

The Champion's plasma pistol is one weapon with two profiles. The attacker
picks a profile each time it shoots.

### Abilities and unique actions (paraphrased)

| Operative | Rule | Kind | Summary |
| --- | --- | --- | --- |
| Champion | Grandfather's Blessing | Passive, triggered | When an enemy that has a Poison token loses wounds within 7" of the Champion, the Champion regains the same number of wounds. Capped at 3 per turning point. Does nothing once the Champion is incapacitated (Aug '26 errata) |
| Bombardier | Grenadier | Passive | Can use blight and krak grenades without spending the team's limited grenade uses. Hit improves by 1 when it does, and its blight grenades gain Toxic |
| Fighter | Flail | Unique action, 1AP | Deals D3+2 damage to every other operative, friend or enemy, that is visible and within 2". An enemy that rolls a 3 on the D3 also gains a Poison token. Counts as a Fight action for action restrictions and Astartes. Cannot be used while the Fighter has a Conceal order |
| Icon Bearer | Icon Bearer | Passive | +1 to its APL when working out marker control. This is not a stat change, so other modifiers stack with it |
| Icon Bearer | Icon of Contagion | Passive | The Contagion ploy costs 0CP while the Icon Bearer is in the opponent's territory |
| Plaguecaster | Poisonous Miasma | Unique action, 1AP, PSYCHIC | Gives one enemy a Poison token. The enemy must be visible and within 7", or otherwise a valid target. If it already has a token, deal 3 damage instead. Cannot be used within control range of an enemy |
| Plaguecaster | Putrescent Vitality | Unique action, 1AP, PSYCHIC | Heals a visible friendly operative within 3". Roll 2D6: a total of exactly 7 heals 7 wounds, otherwise heal the higher die. Cannot be used within enemy control range. Once per turning point |
| Warrior | Repulsive Fortitude | Passive, defensive | When the Warrior is being shot, its defence dice count 5+ as critical successes |
| Heavy Gunner | none | none | No ability is printed on the card |

## Faction rules

| Rule | Summary | AI-relevant hooks |
| --- | --- | --- |
| **Astartes** | In an activation, a Plague Marine can perform two Shoot actions or two Fight actions. Two Shoots must include at least one bolt pistol, boltgun or PSYCHIC weapon. The same PSYCHIC ranged weapon can be picked only once per activation. Every Plague Marine can counteract regardless of its order. | Changes the action economy. The action planner needs per-action-type repeat permission with a weapon constraint, and counteract eligibility that ignores orders |
| **Poison** (weapon rule and token) | In the Resolve Attack Dice step, a Poison weapon that inflicts any damage gives the target one of your Poison tokens. Friendly Plague Marines never get one. A token is binary: an operative cannot hold two of yours. An operative with your token takes 1 damage each time it is activated. | A persistent per-operative status owned by the Plague Marines player. The [core update log][crul] says Poison resolves first among "is activated" effects that inflict damage |
| **Toxic** (team weapon rule) | If the target had one of your Poison tokens at the start of the action, both Dmg stats get +1. Rules commentary for the Bombardier's blight grenade (Blast): apply the bonus only against secondary targets that have a token. This overrides the usual core rule about stat changes mid-action. | A conditional damage modifier that depends on the target's state when the action started. It is checked per target, not per action |
| **Disgustingly Resilient** | When a single attack dice deals 3 or more damage to a Plague Marine, roll a D6. On 4+, reduce that damage by 1. | A defensive damage-reduction step with a dice roll. The [core update log][crul] says rules that ignore Dmg-stat changes cannot ignore it |

## Strategy ploys

The team rules print no CP cost. The [Lite Rules][lite] say every ploy costs
1CP. Strategy ploys are Strategic Gambits, played alternately in the Strategy
phase, and each can be used once per turning point. Icon of Contagion can make
Contagion cost 0CP. The cards print no duration for an ongoing effect such as
Contagion. Taking it to last until the end of the turning point is an
assumption (see uncertainties).

| Ploy | Summary | Duration / trigger |
| --- | --- | --- |
| **Contagion** | An enemy operative gets Move -2" and worsens its weapons' Hit by 1 when either: it has a Poison token and is visible to and within 3" of friendly Plague Marines, or it is visible to and within 3" of the Icon Bearer. This does not stack with the injured penalty. | Assumed to last for the turning point. A proximity aura that depends on poison state |
| **Lumbering Death** | Plague Marines' weapons gain Ceaseless when they shoot or fight in an activation where they moved 3" or less, or when they retaliate. Per the [core update log][crul], the extra distance for climbing or moving through Accessible terrain counts toward the 3". | Assumed to last for the turning point. The engine has to track movement distance within each activation |
| **Cloud of Flies** | Place a Cloud of Flies marker anywhere in the killzone. A Plague Marine wholly within 1" of the marker is obscured to attackers more than 3" away. Remove the marker in the Ready step of the next Strategy phase. | Places a marker that persists until the next Strategy phase |
| **Nurglings** | Pick an enemy within 3" of a Plague Marine, or a poisoned enemy within 7" of one. It gets -1 APL until the end of its next activation. | Targeted debuff |

## Firefight ploys

| Ploy | Summary | Timing |
| --- | --- | --- |
| **Virulent Poison** | One enemy within 3", or visible and within 7", of the active Plague Marine gains a Poison token. The current card has only this effect (see the version discrepancy under uncertainties). | During a Plague Marine's activation or counteraction, before or after an action |
| **Poisonous Demise** | When a Plague Marine is incapacitated, every enemy that is visible and within 3" gains a Poison token. Any enemy that already had a token takes 1 damage instead. | When a Plague Marine is incapacitated, before it is removed |
| **Sickening Resilience** | For the rest of the activation or counteraction, Disgustingly Resilient always subtracts 1 for that operative without a roll. Damage cannot go below 2. | When an attack dice inflicts damage on a Plague Marine |
| **Curse of Rot** | Each 3 the opponent rolls deals 1 damage to their operative, cannot be kept as a success, and cannot be re-rolled. | When a Plague Marine shoots or fights an enemy within 3" (or a poisoned enemy within 7"), after the opponent rolls attack or defence dice |

## Faction equipment

| Equipment | Kind | Summary |
| --- | --- | --- |
| **Plague Bells** | Passive modifier | Plague Marines ignore the stat changes from being injured, including weapon stats. The [Lite Rules][lite] define injured as below half starting wounds: -2" Move and worse Hit |
| **Blight Grenades** | Weapon grant, limited uses | Every Plague Marine gains a blight grenade: ATK 4, HIT 4+, DMG 2/4, Range 6", Blast 2", Saturate, Severe, Poison. The team can use it at most twice per battle. Bombardier uses do not count toward that limit |
| **Plague Rounds** | Weapon-rule grant | All friendly boltguns and bolt pistols gain Poison and Severe |
| **Poison Vents** | Proximity trigger | When an enemy is activated within 3" of a Plague Marine: if it has no token, roll a D3 and it gains one on a 3; if it already has one, it takes D3 damage instead of the usual 1 |

Universal equipment the Bombardier interacts with ([Universal Equipment][ue]):
krak grenade 4 / 4+ / 4/5, Range 6", Piercing 1, Saturate. Frag grenade
4 / 4+ / 2/4. The explosive-grenades selection gives the team 2 grenades in
total, split as 2 frag, 2 krak, or 1 of each.

## Setup and deployment

- The team rules contain **no special deployment, infiltration or pre-battle
  placement rules**. Plague Marines deploy under the mission's standard setup
  sequence (see [killteam-setup-rules.md](killteam-setup-rules.md)).
- None of the four faction equipment items places anything on the table before
  the battle. Universal equipment such as Ammo Cache, Razor Wire or Portable
  Barricade can, if the player selects it ([Universal Equipment][ue]).
- The first faction marker appears in play when **Cloud of Flies** is used in a
  Strategy phase. The first faction tokens are **Poison tokens**, which appear
  once the battle starts.
- Roster selection is the setup-time decision. The AI picks which one of the
  six specialists to leave out, then deploys 6 operatives.

## Tactical summary for the AI

Facts from the rules, with the tactical reading in italics.

- Six bodies with 14–15 wounds, a 3+ save, Disgustingly Resilient and the
  Warrior's Repulsive Fortitude. *The team is very durable and outnumbered, so
  trading efficiency matters more than activation count.*
- Move 5" across the whole team, and Lumbering Death rewards moving 3" or less.
  *Plan short advances and hold positions. Plague Bells removes the injured
  slowdown.*
- Many rules key off Poison tokens: Toxic, Contagion, Nurglings, Curse of Rot,
  Grandfather's Blessing and Poisonous Demise. *Applying tokens early, via
  Miasma, Virulent Poison, Plague Rounds or Poison weapons, unlocks most of the
  team's damage, debuffs and healing. The engine must track which enemies hold
  tokens.*
- Aura distances are almost all **3"** or **7"**, and most also need
  visibility. *The engine needs distance and visibility queries between every
  pair of friendly and enemy operatives.*
- Icon Bearer: APL +1 for marker control, and a free Contagion while in enemy
  territory. *It fits the Security archetype and objective play.*

## Repository observations

The repo does not yet model a Plague Marines team. It currently identifies
them by name text:

- `tts_mcp/runtime/killteam_runtime.py:1036` marks an operative as AI-owned if
  its name contains `plague marine`. Lines 1043–1047 derive `operative_id` and
  `profile_id` (for example `plague_warrior`) from the display name.
- `tts_mcp/runtime/killteam_runtime.py:2545` lists `plague` and `nurgle` among
  "aggressive" faction keyword heuristics. CONTEXT.md's **Team profile** entry
  names this kind of faction heuristic as the thing to avoid.
- `tts_mcp/app/server.py:1799`, `tts_mcp/runtime/killteam_setup_runtime.py:640`,
  `tts_mcp/runtime/killteam_runtime.py:4452` and
  `tts_mcp/runtime/gameplay_runtime.py:432` hard-code the name
  `Plague Marine Warrior`.
- `SAVE_131_FIXTURE_PROFILE` in `killteam_runtime.py` sets the AI faction tags
  to `LEGIONARY` and `Chaos`. In the save the Warrior model is tagged
  `LEGIONARY`, `Operative`, `Chaos`. The official keywords are PLAGUE MARINE,
  CHAOS, HERETIC ASTARTES. LEGIONARY belongs to a different kill team
  (Legionaries). The team profile should map the save's native tags to the
  team explicitly rather than reuse them as faction identity.
- The test fixtures in `tests/test_killteam_runtime.py` (around lines 453 and
  557) give the Warrior's boltgun `"range": 8`. The official boltgun has no
  Range rule. Range 8" belongs to the bolt pistol. The save's own card
  description (`WR: Toxic`, no range) agrees with the official card.
- No code handles Poison tokens, Toxic or Disgustingly Resilient.

## Uncertainties and items not verified from a primary source

- **Base size:** the `32` on each card is read as a 32 mm base. The card does
  not label the number.
- **Weapon type (ranged or melee):** the PDF marks this with icons, which text
  extraction does not keep. The types above follow the weapon names and rules,
  for example Range or Torrent means ranged.
- **Plague wind range:** no Range rule is printed, so the range is taken to be
  unrestricted under Torrent 1".
- **Ploy CP cost:** taken from the Lite Rules, not the full Core Rules. The
  Core Rules are distributed through the Kill Team app and could not be read
  here.
- **Strategy ploy duration:** the cards do not say how long ongoing strategy
  ploy effects last (Contagion, Lumbering Death). Until the end of the turning
  point is the assumed Core Rules default. The Lite Rules do not state it.
- **Equipment selection limit:** how many equipment options a player may take
  per game is set by the full Core Rules (app only) and was not verified. The
  team rules do not set it.
- **PSYCHIC keyword:** what PSYCHIC means for weapons and actions is defined in
  the full Core Rules (app only) and was not verified. The Lite Rules do not
  cover it.
- **Virulent Poison version discrepancy:** the "Previous Errata" section of
  the update log records an older change that added a second option (roll
  2D6, and on 7+ an enemy within 7" gains a token). The current ploy card in
  the same PDF shows only the first option. This page follows the card.
  Confirm with the host whether the 2D6 option still applies.
- **Heavy Gunner ability:** the card text shows none. This matches the weapon
  list, but it is worth a visual check of the PDF page.

## Implications for the team profile schema

A team profile needs these fields to represent Plague Marines:

1. **Identity and provenance:** profile id, schema version, game edition,
   source document URL, source `last_updated` date, errata label
   (`August '26`), and rotation or legality status.
2. **Faction keywords:** the faction keyword (`PLAGUE MARINE`), shared
   keywords (`CHAOS`, `HERETIC ASTARTES`), and per-operative extra keywords
   (`LEADER`, `PSYKER`, the role keyword).
3. **TTS identity mapping:** how a save's native names and tags (for example
   `Plague Marine Warrior` with `LEGIONARY`/`Chaos` tags) map to operative
   types. This replaces name-substring matching.
4. **Archetypes:** a list (`security`, `seek_and_destroy`).
5. **Composition rules:**
   - a required leader slot (exactly 1 Champion)
   - a pick-N-from-list slot (5 from 6)
   - a per-type maximum (1 each)
   - a total operative count
   - expressive enough for other teams' caps, such as the Novitiates' Purgatus
     cap in [killteam-setup-rules.md](killteam-setup-rules.md)
6. **Operative types:**
   - id, display name, keywords
   - APL, Move (inches), Save, Wounds
   - base size (mm)
   - weapon list, plus optional loadout choices (empty for this team, but
     other teams need them)
   - abilities and unique actions
7. **Weapons:**
   - id, name, type (ranged or melee)
   - one or more **profiles** (plasma pistol standard and supercharge)
   - ATK, HIT, normal and critical DMG
   - a structured rules list with parameters: `Range x`, `Piercing x`,
     `Lethal x+`, `Torrent x`, `Blast x`, `Hot`, `Severe`, `Saturate`,
     `Brutal`, `Shock`, `Stun`, `Ceaseless`
   - a `psychic` flag
   - references to team-defined rules (`poison`, `toxic`)
8. **Team-defined weapon rules:** named rules beyond the core set, with their
   trigger point in the attack sequence:
   - Poison applies a token in the Resolve Attack Dice step.
   - Toxic is a damage modifier that depends on the target's state at the
     start of the action, checked per target.
9. **Tokens and markers:**
   - per-operative status tokens that the controlling player owns. Poison is
     binary and can only go on enemies.
   - placeable killzone markers with a lifetime. Cloud of Flies is removed in
     the next Strategy phase's Ready step.
   - for each, its TTS object or tag binding, so the AI can place and read
     them physically
10. **Faction rules as hooks:**
    - action-economy changes (Astartes: repeat Shoot or Fight, with weapon
      constraints)
    - counteract eligibility
    - on-activation triggers (Poison damage)
    - defensive damage reduction, with or without a roll (Disgustingly
      Resilient)
11. **Unique actions:**
    - AP cost and keywords (PSYCHIC)
    - restrictions: not within enemy control range, not with a Conceal order,
      once per turning point
    - "treated as a Fight action" equivalence
    - range and visibility targeting
    - effects: damage, tokens, healing
12. **Ploys:**
    - id, kind (strategy or firefight)
    - base CP cost, plus **conditional cost overrides** (Contagion is 0CP via
      Icon of Contagion)
    - timing trigger, duration, usage limit
    - effect class: aura modifier, marker placement, targeted debuff,
      dice-result reaction
13. **Equipment:**
    - faction and universal equipment references
    - effect class: passive modifier (Plague Bells), weapon grant with a
      team-wide **limited-use counter** and per-operative exemptions (Blight
      Grenades, Grenadier), weapon-rule grant by weapon class (Plague Rounds
      for boltguns and bolt pistols), proximity trigger (Poison Vents)
    - whether it places anything before the battle
14. **Proximity and visibility predicates:** auras defined by distance (2",
    3", 7"), visibility, territory (opponent's territory), and token state.
    The engine needs these as reusable queries.
15. **Per-turning-point and per-activation counters:**
    - healing cap (3 per turning point for Grandfather's Blessing)
    - once-per-turning-point actions
    - distance moved this activation, including terrain surcharges
      (Lumbering Death)
    - battle-wide limited uses (Blight Grenades)
16. **Marker-control modifiers:** APL adjustments that count only for marker
    control (Icon Bearer).
17. **Setup data:** special deployment rules (none for this team) and
    pre-battle placeable equipment (none from faction equipment).
18. **Tactical preferences (non-rule, AI-only):**
    - archetype-driven objective weighting
    - a "poison first" target-priority hint
    - a preferred movement budget (3" or less, for Lumbering Death)
    - roster-cut preference (which specialist to leave out)
    - kept separate from the rules data so preferences never override legality

[pm]: https://assets.warhammer-community.com/eng_plague_marines_online_rules-wqjvit50wj-jvekzllwdl.pdf
[lite]: https://assets.warhammer-community.com/eng_jul25_kt_lite_rules-jmjv4hdamy-qlsqxdf83p.pdf
[ue]: https://assets.warhammer-community.com/eng_17-06_kill_team_key_downloads_universal_equipment-prsd0j8pih-ikfmigl0za.pdf
[crul]: https://assets.warhammer-community.com/eng_17-06_kill_team_key_downloads_core_rules_update_log-9dzdz0ewle-wutcyhpgzf.pdf
[aotc]: https://assets.warhammer-community.com/eng_kt_approved_ops_2025_tournament_companion-fpsaag6ryp-uwnxgflxow.pdf
