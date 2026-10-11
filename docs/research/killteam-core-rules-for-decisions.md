# Kill Team core rules for decision-making

Date checked: 2026-10-11
Ticket: GitHub issue #2 (wayfinder research). Extends
`docs/research/killteam-setup-rules.md` and `game_rules/killteam/rules.md`.

This note lists the rules facts a tactical decision-maker needs for each
decision the Kill Team AI opponent makes. It summarises the rules and does not
reproduce them. Each fact carries a source tag (see [Sources](#sources)). The
tags show how much to trust the fact:

- **Primary (GW PDF)**: read directly from a Games Workshop document
  downloaded from `assets.warhammer-community.com` on the date above.
- **Core Book (transcribed)**: from the Kill Team Core Book. GW does not offer
  the full core rules as a free web PDF. They are free in Kill Team: The App and
  printed in the Core Book. I read them through the Wahapedia transcription,
  which is a **secondary source**. Where a GW errata or Lite rules text quotes
  or matches the same wording, the fact is marked as corroborated. Check these
  facts against the App or Core Book before you encode them as hard legality
  rules.

## Edition status

- The current edition is **Kill Team 3rd edition**, launched with Kill Team:
  Hivestorm in September 2024 ([WC-LAUNCH]). The Approved Ops 2025 Tournament
  Companion (updated 26 Aug 2026) still calls it "3rd edition rules" and lists
  the Tomb World season in the Classified rotation ([AOTC], Classified Format).
- The Core Book has an online update log dated **June '26**. That log is the
  latest core errata and designer's commentary ([CRUL]).
- No new edition has been announced. The Big Autumn Preview (18 Sep 2026)
  revealed Kill Team: Armageddon (Legion of the Damned vs Ork Nobz plus
  Killzone: Armageddon). That is a boxed set inside the current edition
  ([WC-AUTUMN]).
- Precedence ([CORE] Key Principles, Precedence; positions 5 and 6 corroborated
  by [CRUL]). From highest to lowest:
  1. A rule that says it takes precedence.
  2. The online designer's commentary.
  3. A rule from outside the core book.
  4. A rule that says "cannot".
  5. The active operative's controlling player decides.
  6. The player with initiative decides.
- The online rule beats the printed rule whenever they disagree ([AOTC],
  Rulings). The engine should therefore track the date of every rules source it
  encodes.
- The **current Kill Team Lite rules are dated July 2025**
  (`eng_jul25_kt_lite_rules…pdf`) ([LITE25]). The repo's earlier research
  cited the 02.10.24 Lite PDF. The 2025 version only clarifies four weapon
  rules: Accurate, Heavy (now includes counteractions), Severe and Torrent.
  Setup, orders and actions are unchanged.

## 1. Setup

**Matched-play sequence (Approved Ops 2025)** ([AO] game sequence;
corroborated by the GW Volkus Compound mission pack [VC] and Lite [LITE25]):

1. **Set up the battle.** Pick kill teams, the killzone, terrain types, one
   shared crit op and objective markers. Objective markers go on the killzone
   floor, except in Bheta-Decima. Roll off. The winner decides who has
   initiative. The player with initiative picks a drop zone. The other player
   takes the other drop zone and gains the Re-roll initiative card.
2. **Select operatives.** Each player *secretly* chooses operatives within
   their faction's selection rules, then both reveal at the same time. Each
   player *secretly* picks up to **four equipment options**, with no option
   taken twice, then both reveal. Each player **starts with 2CP**. Each player
   *secretly* picks a tac op from one of their team's archetypes (Infiltration,
   Recon, Security or Seek & Destroy).
3. **Set up operatives.**
   - First, players alternate setting up pre-battle equipment, starting with
     the player who has initiative. They place **one item at a time**, not one
     option at a time.
   - Then players alternate setting up **one third of their kill team, rounded
     up**, starting with the player who has initiative.
   - Each operative must be **wholly within its drop zone** and gets a
     **Conceal order**.
4. **Play four turning points.** Initiative is rolled every turning point,
   including the first. Initiative cards modify the roll. During the first
   turning point, each player secretly picks a **primary op** (crit, kill or
   tac) as a STRATEGIC GAMBIT. Each op scores at most 6VP.
5. **End.** Reveal primary ops. Each player scores bonus VP equal to half the
   VP from their primary op, rounded up.

Other setup facts:

- **"Wholly within"** means every part of the thing is within the distance.
  **"Within"** means any part is within it. Measurements go from the closest
  part of a thing. For an operative, measure from its base and ignore the
  model. To or from an *area* of the killzone, measure horizontally only
  ([CORE] Key Principles, Distances; corroborated in part by [CRUL]).
- Something on the centreline can still be wholly within a territory. It is
  then not within the other territory ([CRUL] commentary).
- **Kill Team Lite** without a mission: the player with initiative picks a
  killzone edge. Each drop zone is the area within 3" of that player's edge.
  The default board is 30" x 22" ([LITE25], Set Up).
- With a mission, the mission map defines drop zones, territories and the
  centreline ([AOTC] universal map key; [VC]).
- In the Volkus Compound narrative pack, **Defence** places equipment and
  operatives first, and **Offence** decides initiative in turning point 1
  ([VC] game sequence). Setup order therefore depends on the mission. The
  engine should load the cadence from the mission instead of hard-coding it.

## 2. Orders

When an operative activates, its player picks an order. The operative keeps
that order until it next activates ([CORE] Firefight Phase, Determine Order;
[LITE25]).

| Order | Allows | Prevents |
| --- | --- | --- |
| **Engage** | All actions as normal. Can counteract. | Nothing extra. Is a valid target whenever visible. |
| **Conceal** | Is **not a valid target while in cover**. | Cannot perform **Shoot** or **Charge**. Cannot counteract. Guard is treated as Shoot, so Conceal also blocks Guard. |

- Operatives always start the battle on **Conceal** ([CORE] Orders; [LITE25]).
- The **Silent** weapon rule lets an operative Shoot with that weapon while on
  Conceal ([LITE25] Weapon Rules).
- Engage is the only order that can counteract ([LITE25] Engage Order and
  Counteract).

## 3. Visibility, cover, Obscured and targeting Conceal operatives

- **Visible:** an unobstructed straight line, 1 mm wide, can be drawn from the
  viewer's head to any part of the target model. Bases are ignored. An
  operative is always visible to itself ([CORE] Visible; [LITE25] has the same
  core idea).
- **Intervening:** draw targeting lines from any point of the shooter's base to
  every facing part of the target's base. Anything at least one line crosses is
  intervening. Anything every line crosses is *wholly* intervening. Draw lines
  top-down normally. Draw them in 3D when the operatives are at different
  heights, for example on Vantage ([CORE] Intervening).
- **Cover:** a target is in cover if intervening terrain is within its control
  range (1" and visible). It **cannot be in cover while within 2"** of the
  other operative ([CORE] Cover; [LITE25] Cover).
- **Obscured:** a target is obscured if intervening **Heavy** terrain lies
  between the operatives. Heavy terrain within 1" of *either* operative does
  not count. Only the parts of a feature within 1" are discounted, not the
  whole feature ([CORE] Obscured). Effect when shooting an obscured target
  ([CORE] Shoot step 3):
  - the attacker must discard one success;
  - every critical success counts as a normal success and cannot be turned
    back into a critical.
- The same terrain feature cannot give both cover and obscured. If it would,
  the **defender picks one** for that sequence ([CRUL] errata to Shoot, Select
  Valid Target).
- **Valid target:**
  - An **Engage** operative is a valid target if it is visible.
  - A **Conceal** operative is a valid target only if it is visible **and not
    in cover** ([CORE] Valid Target; [LITE25]).
- **When a concealed operative can be targeted:**
  - It is not in cover from the shooter. Either no intervening terrain is
    within its 1" control range, or the shooter is within 2" of it.
  - The shooter is on **Vantage** terrain, the target is at least 2" lower,
    and the target's only cover is **Light** terrain. The target keeps its
    cover save and gets an improved one: either the cover save counts as a
    critical success, or it retains one more cover save ([CORE] Killzones,
    Vantage).
  - The weapon has **Seek** (Conceal operatives cannot use terrain for cover)
    or **Seek Light** (they cannot use Light terrain for cover). The cover save
    still applies ([LITE25] Weapon Rules).
  - The target is a **Blast** secondary target. Secondary targets are valid
    whatever their order, and they inherit the primary target's cover and
    obscured status ([LITE25]; [CRUL] commentary).
  - A point-blank shot from an operative on Guard (Gallowdark and Tomb World
    only, see section 5).
- Shoot also requires that the target has **no friendly operatives within its
  control range**. You cannot shoot into a melee that involves your own
  operatives ([CORE] Shoot step 2; [LITE25]).
- **Smoke grenade** (universal equipment): an operative wholly inside the
  smoke is obscured to operatives more than 2" away, and the reverse is also
  true. Piercing 2 drops to Piercing 1 against a target inside the smoke unless
  the operatives are within 2" of each other. The smoke lasts for the rest of
  the turning point it is thrown in. In the next Strategy phase, roll a D3: the
  smoke is removed after that many activations, or at the end of that turning
  point if that comes first ([UE]).

## 4. Terrain types

Each *part* of a terrain feature has its own types. A rule that refers to a
type applies only to the parts with that type ([CORE] Killzones, Terrain
Types).

| Type | Decision-relevant effect |
| --- | --- |
| **Heavy** | Large terrain. Can obscure targets. |
| **Light** | Small terrain. Gives cover, never obscures. Other rules treat it differently, for example Vantage and Seek Light. |
| **Blocking** | Gaps that visibility cannot be drawn through. For cover and obscured, the gap counts as the terrain around it. |
| **Vantage** | Upper levels where operatives can end a move or be set up. Operatives can cross non-Vantage terrain but cannot finish on it. Vantage is also Light. Three effects: (1) shooting an Engage target ≥2" lower gives Accurate 1, or Accurate 2 if ≥4" lower; (2) Conceal targets ≥2" lower cannot use Light cover, as described in section 3; (3) Heavy terrain connected to the Vantage terrain that the shooter or target stands on does not obscure. |
| **Accessible** | Operatives can move through it, but it costs an extra 1". Only the centre of the base has to pass through. |
| **Insignificant** | Ignored for climbing and dropping. Operatives move over it flat. |
| **Exposed** | Never intervening for cover or obscured. |
| **Ceiling** (errata) | Operatives on round bases up to 50mm, or the 60x35mm oval, can move underneath it whatever their height. |
| **Wall** (Gallowdark and Tomb World) | Impassable in every case, including Breach markers. Distances are measured around it, except distances to killzone areas ([CRUL] commentary; [CORE] Killzones). |

Sources: [CORE] Killzones, Terrain Types. Ceiling and the Wall commentary are
corroborated by [CRUL]. Each killzone gives its own terrain types per feature,
for example Octarius in [AOTC] and Volkus in [CRUL]. The engine needs a
per-part terrain-type map for each killzone and cannot infer types from shape.

## 5. Actions, APL and movement

**Activation rules** ([CORE] Firefight Phase; [LITE25]):

- Players alternate activations, and the player with initiative goes first.
  Each activation runs in this order:
  1. Choose the order.
  2. Perform actions. The total AP spent cannot exceed the APL, and no action
     can be repeated in the same activation.
  3. The operative is expended.
- The cost of an action never drops below 0AP.
- APL can never change by more than ±1 from its datacard value.
- The Move stat can never drop below 4".
- If an action cannot be completed, it is cancelled. The game state reverts and
  no AP is spent.
- **Counteract** ([CORE]; wording corroborated by [CRUL]):
  - It is possible when all your operatives are expended and your opponent
    still has ready operatives.
  - In place of an activation, one expended **Engage** operative may perform a
    free 1AP action. Guard is excluded.
  - Each operative can counteract once per turning point.
  - While counteracting it can move at most 2", or be set up wholly within 2"
    if it is removed and set up again.
  - Counteracting is optional, and play then alternates back.
  - The 2" cap includes extra distance from Accessible terrain, climbing and
    dropping. In practice, Accessible terrain cannot normally be crossed while
    counteracting ([CRUL] commentary).
- **Injured** means fewer than half the operative's starting wounds remain. An
  injured operative has −2" Move and worsens its weapons' Hit stat by 1
  ([CORE] Damage; [LITE25]).

**Universal actions** ([CORE] Actions; [LITE25]):

| Action | AP | Movement | Key restrictions |
| --- | --- | --- | --- |
| Reposition | 1 | Up to Move, in straight-line increments, each **rounded up to the nearest inch**. Cannot enter enemy control range, unless a friendly operative is already in that enemy's control range. It may then pass through but not end there. | Not while in enemy control range. Not in the same activation as Fall Back or Charge. |
| Dash | 1 | Up to 3". Cannot climb. Can drop and jump. | Not while in enemy control range. Not in the same activation as Charge. |
| Fall Back | 2 | Up to Move. May pass through enemy control range but must not end in it. | Requires an enemy within control range. Not in the same activation as Reposition or Charge. |
| Charge | 1 | Up to Move +2". Must end within enemy control range. Once it is within the control range of an enemy that no other friendly operative is engaging, it cannot leave that enemy's control range. | Not on Conceal. Not if already in enemy control range. Not in the same activation as Reposition, Dash or Fall Back. |
| Shoot | 1 | Not applicable. | Not on Conceal, unless the weapon is Silent. Not while in enemy control range. |
| Fight | 1 | Not applicable. | Requires an enemy within control range. |
| Pick Up Marker | 1 | Not applicable. | Takes a marker the operative controls. Not while in enemy control range. Not if already carrying a marker. |
| Place Marker | 1 | Not applicable. | Places the carried marker within control range. Not in the same activation as Pick Up, unless the operative is incapacitated, in which case it is forced and costs 0AP. |
| Guard (Gallowdark and Tomb World only) | 1 | Not applicable. | Treated as Shoot. Not on Conceal or in enemy control range. Can interrupt once per enemy activation, after an enemy action, to Shoot or Fight for free. Point-blank shots have Hit worsened by 1. An operative that uses this cannot counteract that turning point ([CORE] Killzones, Close Quarters; [CRUL]). |

**Climbing, dropping and jumping** ([CORE] Killzones, Terrain and Movement;
jumping corroborated by [CRUL] errata):

- Operatives cannot move through terrain. They must go around, climb, drop or
  jump. A move must end in a place where the operative can be placed. If it
  cannot, the move cannot begin.
- **Climb:** the operative must be within 1" horizontally and 3" vertically of
  visible terrain. Each climb counts as at least 2" of vertical distance.
- **Drop:** ignore 2" of vertical drop per *action* in total, not per drop.
- **Jump:** only from Vantage terrain higher than 2". The operative moves up to
  4" horizontally in one straight increment, then drops or climbs. If a rampart
  is at the edge, it must climb the rampart first. When landing on a feature,
  it ignores height differences of 1" or less.
- Within one action, add up all vertical distance before rounding. A climb can
  continue onto further terrain within 1" horizontally and 3" vertically
  ([CRUL] commentary with worked examples).
- Extra movement cost from climbing or Accessible terrain counts toward
  distance-limited rules ([CRUL] commentary).
- **Bases:** friendly operatives can move through each other. Operatives
  cannot move through enemies. Bases cannot overlap, enter terrain or hang off
  the killzone edge ([CORE] Bases).

## 6. Control range and objective control

- **Control range:** something is in an operative's control range when it is
  visible to the operative and within 1" of it. Between two operatives this is
  mutual: if it holds for either one, both are in each other's control range
  ([CORE] Control Range; [LITE25]).
- Terrain that blocks sight also blocks control range, even within 1"
  ([CORE] Control Range diagram). Killzone doors are an exception: they are
  ignored for control-range visibility ([CRUL] Volkus; [AOTC] Octarius).
- **Contest and control** ([CORE] Markers):
  - Operatives contest every marker within their control range.
  - A side **controls** a marker when the total APL of its contesting
    operatives is **greater** than the enemy's total. Equal totals mean
    neither side controls it.
  - Control cannot change during an action.
  - An operative carrying a marker is the only one that contests and controls
    it.
- Objective markers are 40mm. Other markers are 20mm ([CORE] Markers).
- A carried mission or objective marker is the same distance as its carrier
  ([CRUL] errata to Distances).
- In Approved Ops, scoring usually happens **at the end of each turning point
  after the first**, so control at that moment is what counts ([AOLOG] crit and
  tac op text, e.g. Stake Claim, Energy Cells, Martyrs).

## 7. Shooting and fighting sequences

**Shoot** ([CORE] Actions, Shoot; [LITE25]):

1. **Select weapon.** Choose one ranged weapon and take Atk dice.
2. **Select valid target.** The target must not have friendly operatives
   within its control range. Work out cover and obscured now. The defender
   picks one if the same terrain feature gives both.
3. **Roll attack dice.** A roll ≥ Hit is a success. A 6 is a critical. A 1 is
   always a fail. If the target is obscured, discard one success and treat
   crits as normals.
4. **Roll defence dice.** Always three dice. A target in cover can keep one
   normal success without rolling it (the cover save). A roll ≥ Save is a
   success, and a 6 is a critical.
5. **Resolve defence dice.** One normal blocks one normal. Two normals block
   one crit. One crit blocks either.
6. **Resolve attack dice.** Unblocked normals deal Normal Dmg. Unblocked crits
   deal Critical Dmg. All successes resolve at the same time ([CRUL]
   commentary). Incapacitated operatives are removed after the whole action,
   which matters for Blast and Torrent.

**Fight** ([CORE] Actions, Fight; [LITE25]):

1. Choose an enemy within control range. That enemy retaliates.
2. Each side picks one melee weapon.
3. Both sides roll at the same time. Each *assisting* friendly operative
   improves the Hit stat by 1. An assisting operative must be within the
   enemy's control range and not within any other enemy's control range. Kill
   Team Lite has no assist rule.
4. Starting with the attacker, the players alternate resolving one die at a
   time. Each die either **strikes** (deals damage now) or **blocks** (cancels
   one unresolved enemy success: a normal blocks a normal, a crit blocks
   either). When one player runs out of dice, the other resolves all their
   remaining dice. The fight stops as soon as one operative is incapacitated.
   A player may block even when no enemy dice remain to block.

- Re-rolls: no die can be re-rolled more than once. When both players can
  re-roll, they alternate starting with the player who has initiative. Dice
  retained automatically, such as cover saves and Accurate, cannot be
  re-rolled ([CORE] Dice; [CRUL]).
- Weapon rules that change these sequences include Accurate, Balanced, Blast,
  Brutal, Ceaseless, Devastating, Heavy, Hot, Lethal, Limited, Piercing,
  Punishing, Range, Relentless, Rending, Saturate, Seek, Severe, Shock, Silent,
  Stun and Torrent. They are summarised in [LITE25] Weapon Rules, which matches
  the Core Book appendix and the [CRUL] errata.

## 8. Universal equipment placement

From [UE], the Universal Equipment PDF and its update log (June '26):

- Each player picks up to four equipment options, each no more than once
  ([AO]). Players set the items up alternately, one at a time, *before* any
  operatives are set up ([AO]; [VC]).
- **Light barricades (x2)** and **portable barricade (x1):** wholly within
  your territory, on the killzone floor, and more than 2" from other equipment
  terrain, access points and Accessible terrain. The barricade feet are
  Insignificant and Exposed. The portable barricade is also Protective, which
  improves Save by 1 to a maximum of 2+, and Portable, which means it only
  gives cover while the operative is connected to it. It has its own Move With
  Barricade action: Move −2", no climbing, dropping or jumping.
- **Heavy barricade (x1):** wholly within **4" of your drop zone**, on the
  killzone floor, and more than 2" from other equipment terrain, access points
  and Accessible terrain. It is Heavy terrain, so it can obscure targets and
  gives a safe place to deploy.
- **Razor wire:** placed like the Light barricades. It is Exposed and
  Obstructing: crossing it within 1" costs an extra 1".
- **Ladders (x2):** wholly within your territory, upright against terrain at
  least 2" tall, more than 2" from other equipment terrain, and more than 1"
  from doors and access points. Once per action, a climb with the ladder in
  control range for the whole climb counts as 1" vertical.
- **Mines:** a marker wholly within your territory, more than 2" from other
  markers, access points and Accessible terrain. The first operative whose
  control range it enters, from either side, takes D3+3 damage and the marker
  is removed.
- **Ammo cache** and **comms device:** markers wholly within your territory,
  with no extra spacing rule. Ammo cache gives the 0AP Ammo Resupply action.
  Comms device adds +3" to SUPPORT distance rules while you control it.
- **Grenades:** a utility pick (smoke or stun) or an explosive pick (frag or
  krak) gives two uses for the whole team in total. Grenades are not placed
  before the battle.
- **Killzone override:** in Bheta-Decima, equipment can go on Vantage terrain
  and within 2" of Accessible terrain ([CRUL] errata).

## 9. Ploys and the CP economy

- **Starting CP:** 2CP each ([AO] Select Operatives; [VC]; [LITE25]).
- **Strategy phase, Ready step:** each player gains 1CP. In every turning
  point after the first, the player *without* initiative gains **2CP** instead.
  CP carries over until spent ([CORE] Strategy Phase, Ready; [LITE25] gives the
  same totals). Across four turning points a player gets 2 + 1 + three more
  gains of 1–2CP, so 6–9CP in total.
- **Gambit step:** starting with the player who has initiative, players
  alternate using one STRATEGIC GAMBIT or passing, until both pass in a row.
  Every strategy ploy is a STRATEGIC GAMBIT. Each gambit can be used at most
  once per turning point ([CORE] Strategy Phase, Gambit; [LITE25]).
- **Firefight ploys** are used during the Firefight phase as each ploy states.
  They cannot be used outside that phase unless the ploy says so ([CRUL]
  commentary).
- **Cost and limits:** every ploy costs 1CP unless it says otherwise. Each ploy
  can be used at most once per turning point, **except Command Re-roll**
  (1CP: re-roll one of your attack or defence dice after rolling), which can be
  used repeatedly ([CORE] Ploys; [LITE25]).
- **Initiative** ([AO] step 4):
  - Players roll off every turning point, including the first, and ties are not
    re-rolled.
  - Players then alternate playing initiative cards or passing, starting with
    the player losing the roll.
  - The winner decides who has initiative.
  - A tie goes to the player who does not currently have initiative.
  - The roll-off loser gains the initiative card numbered after the current
    turning point, except in turning point 4.
  - Initiative decides who activates first and who resolves simultaneous
    rules. Losing initiative gives +1CP, which is a real trade-off for the
    engine to weigh.

## 10. Kill Team Lite differences

Compared with the Core Book and Approved Ops ([LITE25] vs [CORE]/[AO]):

| Topic | Lite | Core Book / Approved Ops |
| --- | --- | --- |
| Drop zones | No mission: within 3" of each player's chosen edge. | Taken from the mission map. |
| Setup | One third, rounded up, alternating, wholly within the drop zone, Conceal order. | Same, but equipment goes down first, item by item. Selections are secret. |
| Initiative | Initiative is assigned at random during setup. Each Strategy phase uses a D6 roll-off. | Approved Ops uses roll-offs with initiative cards and the Re-roll card. |
| Reposition | Cannot move within enemy control range at all. | May pass through an enemy's control range if a friendly operative is already engaging that enemy. |
| Counteract | 1AP free action, 2" cap. | Also excludes Guard and caps set-up distance at 2". |
| Obscured / Heavy | Not present. | Present: discard one success and turn crits into normals. |
| Terrain types, Vantage, climb, drop, jump | Absent. Lite only says Dash cannot climb. | Full rules (sections 4–5). |
| Markers and objectives | Pick Up and Place Marker and the APL-based control rule are absent. | Present. |
| Fight assists | Absent. | +1 Hit per assisting operative. |
| Equipment, tac ops, primary op | Absent. | Present in Approved Ops. |
| CP | 2 at the start, +1 each in turning point 1, then 1 for the player with initiative and 2 for the other. | Same totals. |

## Hidden information (relevant to ADR 0005)

Approved Ops has several secret choices:

- operative selection, revealed at the same time;
- equipment selection, revealed at the same time;
- the **tac op**, which stays hidden until its own reveal condition;
- the **primary op**, which stays hidden until the end of the battle.

([AO]; [AOLOG] shows reveal conditions for each tac op.)

The AI must commit its own secret choices without seeing the opponent's. It
must not infer them from private TTS state. The engine should keep secret
selections out of observations, as ADR 0005 requires.

## Unverified or open items

1. **The full core rules were read only through a secondary transcription.**
   This covers obscured, Vantage, terrain types, climbing and dropping,
   markers and objective control, the CP Ready step, fight assists, Pick Up and
   Place Marker, and the Approved Ops game sequence. GW errata text or the GW
   Lite PDF corroborates many of these, but not all. A human should check them
   against Kill Team: The App or the Core Book before they become hard
   legality checks. The Volkus Compound PDF only shows that Volkus terrain is
   on Core Book pages 62–65, and the update log only shows that Terrain and
   Movement is on page 56. I did not verify other page numbers, so citations
   use section names.
2. **Approved Ops 2025 card pack:** I did not read the cards themselves. The
   game sequence comes from the Wahapedia transcription and is corroborated by
   the GW Volkus Compound PDF, whose sequence matches in each step.
   Crit op and kill op scoring tables were not captured.
3. **"One third rounded up" with uneven or small teams:** the rules do not
   spell out the batch arithmetic. For 10 operatives, the likely reading is
   batches of 4, 4 and 2. Each player probably uses their own team size. Both
   points are unconfirmed.
4. **Territory geometry:** the general definition of "territory" comes from
   mission maps. I did not find a primary text that defines it, beyond the map
   key and the centreline commentary. Equipment placement depends on it.
5. **Lite initiative in turning point 1:** Lite assigns initiative at random
   during setup, and its Strategy phase also says to roll each turning point.
   Whether turning point 1 rolls again is ambiguous.
6. **Killzone-specific rules** are out of scope here. Each killzone needs its
   own terrain-type map, and close-quarters killzones add Guard and walls.
   Examples: Gallowdark, Tomb World, Volkus, Bheta-Decima, Octarius and the new
   Armageddon killzone.

## Sources

- [LITE25] Games Workshop, *Kill Team Lite Rules* (July 2025),
  <https://assets.warhammer-community.com/eng_jul25_kt_lite_rules-jmjv4hdamy-qlsqxdf83p.pdf>
  — primary. The earlier 02.10.24 version is at
  <https://assets.warhammer-community.com/rules-downloads/kill-team/key-downloads/kill-team-lite-rules/killteam_keydownloads_literules_eng_02.10.24.pdf>.
- [CRUL] Games Workshop, *Core Rules: Update Log* (Core Book, June '26),
  <https://assets.warhammer-community.com/eng_17-06_kill_team_key_downloads_core_rules_update_log-9dzdz0ewle-wutcyhpgzf.pdf>
  — primary.
- [UE] Games Workshop, *Universal Equipment* with update log (June '26),
  <https://assets.warhammer-community.com/eng_17-06_kill_team_key_downloads_universal_equipment-prsd0j8pih-ikfmigl0za.pdf>
  — primary.
- [AOTC] Games Workshop, *Approved Ops 2025 Tournament Companion* (updated
  26 Aug 2026),
  <https://assets.warhammer-community.com/eng_kt_approved_ops_2025_tournament_companion-fpsaag6ryp-uwnxgflxow.pdf>
  — primary.
- [AOLOG] Games Workshop, *Approved Ops: Update Log* (August '26),
  <https://assets.warhammer-community.com/eng_kt_approved_ops_update_log-c46bfdlsms-senqgrexsi.pdf>
  — primary.
- [VC] Games Workshop, *Volkus Compound Mission Pack* (April 2025),
  <https://assets.warhammer-community.com/eng_kt_volkus_compound_mission_pack-oai8j5hmhd-a6ugpgdgkj.pdf>
  — primary, with a full PvP game sequence.
- [CORE] *Warhammer 40,000 Kill Team: Core Book* (3rd ed., version noted as
  June 2026), read through the Wahapedia transcription:
  <https://wahapedia.ru/kill-team3/the-rules/core-rules/> and
  <https://wahapedia.ru/kill-team3/the-rules/killzones/> — **secondary**.
- [AO] *Approved Ops 2025* game sequence, read through
  <https://wahapedia.ru/kill-team3/the-rules/approved-ops-2025/> —
  **secondary**, corroborated by [VC].
- [WC-LAUNCH] Warhammer Community, "Saturday Pre-orders: A New Edition Begins
  in Kill Team: Hivestorm" (21 Sep 2024),
  <https://www.warhammer-community.com/2024/09/21/saturday-pre-orders-a-new-edition-begins-in-kill-team-hivestorm/>.
- [WC-AUTUMN] Warhammer Community, "The Big Autumn Preview: the Legion of the
  Damned enter the killzone" (Sep 2026),
  <https://www.warhammer-community.com/en-gb/articles/ltbqrokb/the-big-autumn-preview-the-legion-of-the-damned-enter-the-killzone/>.
- Download index: GW Kill Team downloads,
  <https://www.warhammer-community.com/en-gb/downloads/kill-team/>. The list was
  enumerated through the site's downloads search API on the date checked.
