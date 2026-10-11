# Decision-making approaches for skirmish wargame AI

Date checked: 2026-10-11

Ticket: [#4](https://github.com/Cordenstal/TTS-MCP-server/issues/4) (wayfinder
research). This is input for
[#7 Tactical engine architecture and live path](https://github.com/Cordenstal/TTS-MCP-server/issues/7).
The final section is a **recommendation, not a decision**.

## Question

Which decision-making approaches suit an AI for a turn-based skirmish wargame
like Kill Team? The constraints are:

- alternating activations
- dice outcomes the AI cannot know in advance
- roughly 6–14 operatives per side
- a few seconds per decision on a desktop
- a pure-Python implementation
- decisions a human player can follow

The approaches compared are utility AI, influence or threat maps, rollout
search (MCTS, including chance nodes), goal-oriented action planning (GOAP),
hierarchical task networks (HTN), and hybrids. For each one, this document
covers:

- how it handles one-off setup placement compared with repeated in-game
  choices
- how it's tuned and evaluated
- how explainable it is
- what it costs to build

## Constraints from this project and from the rules

These come from `CONTEXT.md`, ADR-0005, ADR-0009 and the official Kill Team
Lite rules. They change how the approaches compare.

1. **The decision unit is one activation.** In the Lite rules, players
   alternate activating ready operatives. Each activation picks an Engage or
   Conceal order, then spends AP up to the operative's APL. A battle is four
   turning points, and initiative is rolled at the start of each one. An
   expended Engage operative can *counteract* for a free 1AP action when its
   side has no ready operatives
   ([Kill Team Lite Rules](https://assets.warhammer-community.com/rules-downloads/kill-team/key-downloads/kill-team-lite-rules/killteam_keydownloads_literules_eng_02.10.24.pdf)).
   So the AI never commits a whole side's turn at once. The opponent answers
   after every activation.
2. **Dice are small and exact.** Attackers roll their weapon's attack dice.
   Defenders roll three defence dice for shooting. 6s are critical, and blocks
   follow fixed normal and critical rules (same source). For a single attack,
   the full distribution of outcomes can be counted exactly. You don't need to
   sample it (see "Chance and hidden information").
3. **No hidden-information cheating.** The AI sees only visibility-safe state
   (ADR-0005, ADR-0009, the "Visibility-safe observation" entry in
   `CONTEXT.md`). Any lookahead may only model unknowns from what the AI is
   allowed to know. It must never use the actual hidden state or a dice result
   that hasn't been rolled yet.
4. **Re-observe after every action, and stop when unsure.** ADR-0009 needs a
   fresh observation before each activation and attack, and a replan when state
   changes. "Uncertainty stop" and "Fail-fast plan" in `CONTEXT.md` forbid
   best-effort guessing. Long-range plans will be thrown away often, so the
   policy has to make good decisions from the current state alone.
5. **The rules engine is the authority.** Rules that aren't modelled and
   conflicts between geometry and evidence pause for a host ruling (ADR-0009).
   The decision layer chooses among legal candidates and never decides legality
   itself.
6. **Live LOS is a TTS probe.** The repository's line-of-sight check is a 9-ray
   probe that runs inside TTS (issue #1, starting-point notes). Search can't
   call it thousands of times. Any lookahead needs an internal geometric
   LOS/cover model.
7. **Explanations reach players as plain text.** The AI announces a plan
   before acting ("Announced plan" in `CONTEXT.md`). Chat must contain only
   natural language and never state dumps (`AGENTS.md`). The decision layer
   therefore has to produce structured reasons that can be turned into a
   sentence.

## How big the problem is (estimate)

This is a back-of-envelope estimate, not a measurement. One AI activation means
choosing:

- one of up to ~14 ready operatives
- one of 2 orders
- a sequence of up to APL (2–3) actions, including a movement destination and a
  target or weapon

Movement is continuous, so destinations must be sampled. Even after pruning to
~20 destinations and a few targets, one activation has roughly 10² to 10⁴
candidates.

For comparison:

- **Xenonauts 2:** about 12 options per unit across 16 units, giving 12¹⁶
  combinations per turn
  ([Roelofs, *Game AI Pro 3* ch. 28](http://www.gameaipro.com/GameAIPro3/GameAIPro3_Chapter28_Pitfalls_and_Solutions_When_Using_Monte_Carlo_Tree_Search_for_Strategy_and_Tactical_Games.pdf)).
- **Blood Bowl:** turn-wise branching estimated at about 10⁵⁰
  ([Justesen et al., CoG 2019](https://pure.itu.dk/en/publications/blood-bowl-a-new-board-game-challenge-and-competition-for-ai/)).

Alternating activations split the turn into small pieces. Roelofs had to build
that split into the Xenonauts search tree ("hierarchical expansion"), but Kill
Team's rules already provide it. Kill Team is still hard to search for three
reasons:

- The horizon is long (a whole turning point holds up to ~28 alternating
  activations).
- The opponent is a human who isn't modelled.
- The evaluation needs LOS and cover, which are expensive to compute.

## Approaches

### 1. Utility AI, including tactical position selection

**What it is.** Each option is scored by combining normalised
*considerations* (inputs mapped through response curves). The best option
runs, or one is picked by weighted random
([Graham, *GAP* ch. 9](http://www.gameaipro.com/GameAIPro/GameAIPro_Chapter09_An_Introduction_to_Utility_Theory.pdf);
[Lewis, *GAP3* ch. 13](http://www.gameaipro.com/GameAIPro3/GameAIPro3_Chapter13_Choosing_Effective_Utility-Based_Considerations.pdf);
[Mark & Dill, GDC 2010](https://gdcvault.com/play/1012410/Improving-AI-Decision-Modeling-Through)).
Variants:

- **Dual utility** adds a *rank* (priority category) on top of the *weight*.
  Urgent categories then always win, and selection inside a category stays
  graded
  ([Dill, *GAP2* ch. 3](http://www.gameaipro.com/GameAIPro2/GameAIPro2_Chapter03_Dual-Utility_Reasoning.pdf)).
- **Tactical position selection (TPS)** is the spatial form: generate candidate
  points, filter them with hard conditions, score them with weights, and use a
  fallback query if nothing passes. Every stage can be logged
  ([Jack, *GAP* ch. 26](http://www.gameaipro.com/GameAIPro/GameAIPro_Chapter26_Tactical_Position_Selection.pdf)).

**Precedents.**

- **XCOM 2** scores each candidate tile as a weighted sum of:
  - cover
  - distance
  - flanking
  - enemy and ally visibility
  - height
  - priority-target distance
  - an optional random term

  The weights come from per-unit-type "move profiles", and behaviour trees
  decide when to move. A per-tile `DebugScore` records the breakdown
  ([`XGAIBehavior.uc` L2209–2223](https://github.com/X2CommunityCore/X2WOTCCommunityHighlander/blob/master/X2WOTCCommunityHighlander/Src/XComGame/Classes/XGAIBehavior.uc#L2209-L2223)).
  Targets are scored by behaviour-tree nodes that add hit chance and distance
  into a target score
  ([`X2AIBTDefaultActions.uc`](https://github.com/X2CommunityCore/X2WOTCCommunityHighlander/blob/master/X2WOTCCommunityHighlander/Src/XComGame/Classes/X2AIBTDefaultActions.uc)).
- **Battle for Wesnoth** (open-source, turn-based, dice-driven). Its default
  RCA AI scores every *candidate action*, runs the best one, and re-evaluates
  until nothing scores above zero
  ([Wesnoth wiki: RCA AI](https://wiki.wesnoth.org/RCA_AI)). The attack rating
  uses exact battle outcome distributions:
  `chance_to_kill*target_value - avg_losses*(1-aggression)`, minus an
  *exposure* term built from enemy "vulnerability" against friendly "support".
  Designers tune it through `aggression` and `caution`
  ([`src/ai/default/attack.cpp` L268–312](https://github.com/wesnoth/wesnoth/blob/master/src/ai/default/attack.cpp#L268-L312)).
  This is the closest open-source analogue to a Kill Team target-selection
  scorer.
- **Bot Bowl:** scripted, heuristic bots won Bot Bowl I and II. In Bot Bowl II,
  the scripted Scripted Plus Bot beat the MCTS bot Sapling 10–0
  ([Bot Bowl II results](https://github.com/njustesen/botbowl/blob/main/docs/bot-bowl-ii.md)).

**Setup compared with in-game.**

- **Setup:** a TPS query over the drop zone (legal and wholly within, no
  overlap, cover from enemy lanes, objective reach, spacing). Operatives are
  assigned to slots as a team, and the plan is redone after each human batch.
  The current `_setup_candidate_plan` (a 5×5 grid with a cover heuristic) is a
  rough version of this.
- **In-game:**
  - Activation choice: score each ready operative's best activation.
  - Movement: a TPS query.
  - Target and weapon: expected damage times target value.

  The same scorer serves every decision area, and each area adds its own
  considerations.

**Stochasticity.** The scorer uses expectations or probabilities, such as
"chance to incapacitate" or "expected wounds". Risk attitude is a tunable
weight, like Wesnoth's `aggression`.

**Tuning and evaluation.**

- Hand-tuned weights checked against scenario tests.
- Weights can be searched automatically. EvoGrod evolved the 16 heuristic
  parameters of GrodBot
  ([Bot Bowl I](https://github.com/njustesen/botbowl/blob/main/docs/bot-bowl-i.md)).
- Self-play tournaments between weight sets.

**Weakness:** utility AI is myopic. It misses combinations that only pay off
several moves later (Roelofs, ch. 28 §28.2).

**Explainability: high.** Every choice comes with its top alternatives and a
per-consideration breakdown.

**Cost: low.** It's plain Python with no forward model needed. Most of the
effort goes into choosing considerations.

### 2. Influence and threat maps

**What it is.** An influence map is a *representation*, not a decision-maker.
It "doesn't actually provide instruction — it only provides information that
is used by the decision-making structures"
([Mark, *GAP2* ch. 30](http://www.gameaipro.com/GameAIPro2/GameAIPro2_Chapter30_Modular_Tactical_Influence_Maps.pdf)).
Layers such as threat, proximity and ally support are combined with
add, multiply and invert operations, then queried. Grids aren't required
([Lewis, *GAP2* ch. 29](http://www.gameaipro.com/GameAIPro2/GameAIPro2_Chapter29_Escaping_the_Grid_Infinite-Resolution_Influence_Mapping.pdf)).
The same idea works at strategic scale
([Dill, *GAP2* ch. 31](http://www.gameaipro.com/GameAIPro2/GameAIPro2_Chapter31_Spatial_Reasoning_for_Strategic_Decision_Making.pdf)).

**Kill Team fit.** Radial falloff is wrong for Kill Team. Threat depends on
LOS, cover and movement plus weapon range. A useful threat layer is "expected
damage visible enemy *e* could deal to a model at point *p* in its next
activation", summed over visible enemies only (ADR-0005). The same goes for
"support" (friendly coverage) and "objective control" layers. Wesnoth's
vulnerability against support is this idea in production (`attack.cpp`
above).

**Setup compared with in-game.**

- **Setup:** layers come from static terrain plus the enemy drop zone, then
  update as enemies are placed.
- **In-game:** maps are recomputed per activation from fresh observation and
  feed utility considerations: avoid high threat, prefer high support, reach
  objectives.

**Tuning:** layer weights and response curves are tuned along with the
utility weights.

**Explainability: high, if visualised.** A heatmap shows "why here", and these
maps fit `docs/wiki/observation-and-visuals.md`.

**Cost: low to medium.** The main cost is the internal LOS/cover model. That
model is needed by every approach anyway (constraint 6).

### 3. Rollout-based search (MCTS and relatives)

**What it is.** The search runs simulated play-outs from candidate moves and
builds a tree with UCT selection. It's an *anytime* algorithm, so it returns
the best move found so far when time runs out
([Sturtevant, *GAP2* ch. 25](http://www.gameaipro.com/GameAIPro2/GameAIPro2_Chapter25_Monte_Carlo_Tree_Search_and_Related_Algorithms_for_Games.pdf);
[Browne et al. 2012 survey](https://doi.org/10.1109/TCIAIG.2012.2186810)).
It needs a fast, copyable forward model. Goodman, Risi and Lucas call this
"a key aspect of game difficulty for AI". They also say statistical forward
planning gives sensible behaviour "out of the box", with no training
([*AI and Wargaming*, 2020](https://arxiv.org/abs/2009.08922)).

**What makes it work in tactics games** (Roelofs, ch. 28, Xenonauts 2 with a
squad of 12 and Berlin):

- **Split a move into per-unit actions and order them sensibly.** Xenonauts 2
  explored attacks and abilities before movement, starting with units nearest
  the player.
- **Prune action sets that heuristics already settle.** Units far from the
  fight just moved to cover or toward the fight, and only *engaged* units were
  searched.
- **Use heuristic or epsilon-greedy play-outs**, not random ones.
- **Abstract the simulation.** Inside play-outs, soldiers became a computed
  strength plus a position used for cover and LOS.
- **Shape the evaluation.** MCTS "has a poor track record for tactical
  decision-making" when the winning line is narrow. A heavy penalty for losses
  speeds up convergence.

In Berlin, this MCTS won 73% and drew 15% against the best utility-based
hierarchical AI.

**Hierarchical Portfolio Search (HPS)** narrows the space further. A
*portfolio* of hand-written partial players proposes a few candidate
sub-moves, and the search runs only over those
([Churchill & Buro, *GAP3* ch. 30](http://www.gameaipro.com/GameAIPro3/GameAIPro3_Chapter30_Hierarchical_Portfolio_Search_in_Prismata.pdf)).
Prismata's difficulty levels used the same portfolio:

- **Master Bot:** a 3 s MCTS search over the portfolio. It reached the top 25%
  of the human ranked ladder.
- **Expert Bot:** a 2-ply alpha-beta search, typically under 100 ms.
- **Medium Bot:** picks a random move from the portfolio.

The bot survived more than 20 balance patches. The AI and Wargaming review
also notes that MicroRTS winners "use a two-level hierarchical approach to
select amongst scripts", which is the same idea.

**Online evolutionary planning** evolves whole-turn action sequences instead of
building a tree. In Hero Academy, a multi-action turn-based tactics game, it
beat constrained MCTS variants as the number of actions per turn grew
([Justesen et al., IEEE TCIAIG 2017](https://pure.itu.dk/en/publications/playing-multi-action-adversarial-games-online-evolutionary-planni/)).
In Kill Team each decision is only up to APL actions, so this advantage
mostly doesn't apply.

**Precedents.**

- **Total War: ROME II** used MCTS for campaign-level task and resource
  allocation, looking about one turn ahead before play-outs. Earlier Total War
  titles used GOAP. This is reported second-hand
  ([Thompson, "The AI of Total War" part 3](https://www.gamedeveloper.com/design/revolutionary-warfare-the-ai-of-total-war-part-3-)),
  and the primary source, Tim Gosling's 2015 Game AI Conference talk, wasn't
  accessible.
- **Warhammer 40k:** a hobby project (40KLearn) reportedly used neural-network
  guided MCTS. Its repository returned 404 on the check date, so it isn't
  relied on here.
- **Bot Bowl:**
  - MCTS bots were uncompetitive early on: Sapling lost every game in Bot
    Bowl II.
  - Learned bots took over later. MimicBot (imitation plus reinforcement
    learning) won Bot Bowl III
    ([Pezzotti 2021](https://arxiv.org/abs/2108.09478)).
  - Drefsante won Bot Bowl IV and V
    ([Bot Bowl IV](https://github.com/njustesen/botbowl/blob/main/docs/bot-bowl-iv.md),
    [Bot Bowl V](https://github.com/njustesen/botbowl/blob/main/docs/bot-bowl-v.md)).
  - Bot Bowl V allowed "2 minutes per turn and 15 seconds per decision in the
    opponent's turn". That's a much larger budget than this project has.

**Setup compared with in-game.**

- **Setup: poor fit.** The value of a deployment shows only after many
  activations, so play-outs from setup are long and noisy. Use heuristics, as
  Roelofs did for non-engaged units.
- **In-game: good fit for activation choice and engaged-operative actions**,
  when given a portfolio of utility-generated candidates and a short horizon,
  such as the rest of the turning point or a fixed number of activations
  followed by a heuristic evaluation.

**Stochasticity.** See "Chance and hidden information" below.

**Tuning and evaluation.**

- Settings to tune:
  - the evaluation function
  - the play-out policy
  - the exploration constant
  - the minimum visits per child (Roelofs suggests about 20)
  - the time budget
- Measure strength with self-play round robins, as Prismata did with 10,000
  games per pairing.

**Explainability: medium to low.** "I chose X; it averaged 0.62 over 800
simulated futures, compared with 0.55 for Y" is honest but not intuitive.
Portfolio search helps, because each candidate already has a readable name
like "focus fire on wounded Plague Marine" or "fall back to cover".

**Cost: high in pure Python.**

- Rules engine work: it needs a fast, copyable forward model of movement, LOS,
  attacks and objectives that runs entirely in memory, with no TTS calls.
- Throughput: Python runs the tree and play-outs much slower than C++ or Java
  engines. A few seconds may allow only hundreds to low thousands of shallow
  play-outs. This is an estimate and needs a benchmark (see open questions).

### 4. Goal-Oriented Action Planning (GOAP)

**What it is.** A* search over actions with symbolic preconditions and effects,
toward a goal world state. It was first used in *F.E.A.R.*
([Orkin, GDC 2006](https://pages.cs.wisc.edu/~dyer/cs540/handouts/gdc2006_orkin_jeff_fear.pdf)).
It's good when an agent needs long chains of preconditions it can't work out
by hand.

**Kill Team fit: poor.**

- Activations are short (APL 2–3) and the rules engine can list them directly,
  so the planning search isn't needed.
- The interesting difficulty is *which* goal to pursue against an adversary
  under dice. GOAP doesn't model opponents or chance (effects are
  deterministic), so it would still need utility scoring to pick goals and
  costs.
- Earlier Total War titles used GOAP. Thompson's article reports problems
  serious enough that later titles replaced it (secondary source).
- Humphreys reports that HTN on *Transformers: Fall of Cybertron* was
  "considerably faster than our GOAP system" in *Transformers: War for
  Cybertron*
  ([*GAP* ch. 12](http://www.gameaipro.com/GameAIPro/GameAIPro_Chapter12_Exploring_HTN_Planners_through_Example.pdf)).

**Setup compared with in-game.** Not useful for setup placement, because
placement is a spatial optimisation and not an action chain. It's marginal for
multi-step mission actions such as moving to a marker and then performing an
action.

**Explainability: medium** (the output is a goal plus an action list). **Cost:
medium**, mostly for little benefit here.

### 5. Hierarchical Task Networks (HTN)

**What it is.** Designer-written *methods* break compound tasks down into
primitive actions, with preconditions on a world state. Search only goes as
far as the domain allows, which makes HTN fast and predictable (Humphreys,
ch. 12). Examples:

- **Killzone 2** used an HTN planner based on SHOP for multiplayer bots, with a
  commander, then group leaders, then individual bots
  ([Verweij 2007](https://www.guerrilla-games.com/media/News/Files/VUA07_Verweij_Hierarchically-Layered-MP-Bot_System.pdf)).
- For wargames, van der Sterren plans multi-unit combat manoeuvres in *plan
  space*. The team-level task comes first, with details added later
  ([*GAP* ch. 13](http://www.gameaipro.com/GameAIPro/GameAIPro_Chapter13_Hierarchical_Plan-Space_Planning_for_Multi-unit_Combat_Maneuvers.pdf)).

**Kill Team fit: as a doctrine layer, not as the core.** HTN captures team-level
intent that a per-activation scorer doesn't see. Examples:

- "Deploy: screen first, then fire base, then objective runners."
- "This turning point: hold objective A with two operatives, threaten B."

Such methods would naturally live in the **team profile** (Plague Marines
first). HTN doesn't evaluate the *quality* of options or handle dice, so method
choice and leaf decisions still need utility scoring.

**Setup compared with in-game.**

- **Setup:** good. Role templates decompose into slot queries.
- **In-game:** good for assigning operatives to roles and objectives per
  turning point. Leaf choices are left to utility scoring.

**Tuning:** designers edit methods and their order. **Explainability: high**
("following *hold objective A*, because…"). **Cost: medium.** A small
domain-specific HTN is about a few hundred lines of Python, but writing the
domain is ongoing work.

### 6. Hybrids used in comparable games

Most shipped and competition tactics AIs are layered hybrids:

| System | Strategic/assignment layer | Per-unit decision | Spatial reasoning | Search |
|---|---|---|---|---|
| XCOM 2 (`XGAIBehavior.uc`) | Behaviour tree | BT nodes and target score | Weighted tile scoring per move profile | None |
| Gears Tactics ([Siemonsmeier 2021](http://www.gameaipro.com/GameAIProOnlineEdition2021/GameAIProOnlineEdition2021_Chapter03_Gearing_the_Tactics_Genre_Simultaneous_AI_Actions_in_Gears_Tactics.pdf)) | Fuzzy goal assignment with priorities | Behaviour tree per assignment | Environment queries | Simulated WorldState, no lookahead |
| Wesnoth RCA AI | Candidate-action loop | Utility with exact battle distributions | Vulnerability against support | None (exact one-ply expectation) |
| Xenonauts 2 (Roelofs) | Heuristics for non-engaged units | Heuristics | Cover and LOS model | MCTS over engaged units |
| Prismata (HPS) | Portfolio of scripted partial players | Scripts | n/a | MCTS or alpha-beta over the portfolio |

Gears Tactics teaches two lessons that apply here:

- **Never plan on dice results.** Each queued ability is simulated into the
  planning WorldState only *after* the unit commits. Otherwise "enemies [would
  be] never taking a shot they would miss … which would be cheating". This
  matches ADR-0005.
- **Throw the plan away when reality differs.** Execution stops and the plan is
  rebuilt when results don't match the planning WorldState. This matches
  ADR-0009's re-observe-and-replan rule. Gears Tactics also kept per-unit
  planning logs, which are useful as a debugging and explanation model.

## Chance and hidden information

**Single attacks can be computed exactly.** Here is my own analysis of the
Lite rules (constraint 2):

- A shooting attack with *a* attack dice gives at most C(a+2, 2) ordered
  (miss, normal, crit) counts. That's 28 for a = 6.
- Three defence dice give 10 counts.
- Weapon rules (Piercing, Accurate, Rending, Lethal, re-rolls) change the
  per-die probabilities or the post-roll steps.

Enumeration is still a few hundred cases, which is cheap even in Python. The
evaluator can therefore use the **exact damage distribution**, including
P(incapacitate). Like Wesnoth's `chance_to_kill`, this is better than a single
average, because a 40% kill chance and a guaranteed 3 wounds aren't equivalent.
Fights alternate strike-or-block choices between both players. They need a
small policy for each side (for example greedy) before the outcome can be
computed. Kill Team fights look small enough to solve exactly with expectimax,
though this hasn't been measured.

**Lookahead with chance nodes.** Options from cheapest to most general:

1. **One-ply expectimax.** Score each candidate activation by the expected
   utility over its exact outcome distribution. This is what Wesnoth does in
   effect. It needs no forward model beyond one attack.
2. **MCTS with explicit chance nodes.** Action nodes alternate with chance
   nodes, outcomes are sampled from the forward model, and children are keyed
   by outcome. The Bot Bowl Python tutorial implements exactly this:
   `ActionNode`/`ChanceNode`, `game.revert(step)`, and a heuristic at the end
   of the turn
   ([botbowl MCTS tutorial](https://github.com/njustesen/botbowl/blob/main/docs/mcts.md)).
   With dense randomness, the same state rarely repeats, so chance nodes need
   sparse sampling or progressive widening
   ([Lanctot et al., *Monte Carlo \*-Minimax Search*, IJCAI 2013](https://arxiv.org/abs/1304.6057)).
   With exact attack distributions you can instead branch on a few bucketed
   outcomes (miss, wounded, incapacitated), weighted by probability.
3. **Hidden information.** Where the mission pack hides choices (for example
   secret selections), **Information Set MCTS** searches over information sets
   using sampled determinisations
   ([Cowling, Powley & Whitehouse 2012](https://doi.org/10.1109/TCIAIG.2012.2200894)).
   The AI and Wargaming review also says practical systems "sample from some
   estimate of the unknown State Space". To fit ADR-0005, samples must come
   from public priors such as the roster pool or rules. They must never come
   from the real hidden state.

## Comparison

| Approach | Setup placement | Activation choice | Movement | Target/weapon | Dice handling | Explainability | Pure-Python cost |
|---|---|---|---|---|---|---|---|
| Utility + TPS | Good | Good (myopic) | Good | Good | Expectations and probabilities | High | Low |
| Influence/threat maps | Input layer | Input layer | Input layer | Input layer | Expected-damage layers | High (heatmaps) | Low–medium (LOS model) |
| MCTS / portfolio search | Poor | Best potential | Over candidates | Over candidates | Chance nodes | Medium–low | High (forward model, speed) |
| GOAP | Poor | Weak | Weak | Weak | None natively | Medium | Medium |
| HTN | Good (doctrine) | Role assignment | Defers to leaves | Defers to leaves | None natively | High | Medium |
| Layered hybrid | Good | Good, and better with search | Good | Good | Exact one-ply, optional search | High | Low, then medium |

Common tuning and evaluation practice from the sources:

- **Scenario tests:** fixed positions with an expected or forbidden choice.
- **Self-play round robins between variants:** Prismata ran 10,000 games per
  pairing, and Bot Bowl runs 10 games per pairing.
- **Parameter evolution:** EvoGrod.
- **Per-decision logs with score breakdowns:** XCOM 2 `DebugScore`, the Gears
  Tactics visual logger, Wesnoth `LOG_AI`.
- **Telemetry on planning time:** Gears Tactics.

## Recommendation (not a decision)

> **Recommendation for #7, to be confirmed by grilling:** build a layered
> hybrid. Utility scoring sits over a shared threat and cover representation,
> with exact one-ply dice expectations. HTN-style team-profile doctrine handles
> setup and role assignment. A bounded portfolio search for activation choice
> is a later, benchmark-gated add-on, not part of the first build.

Proposed layers, in build order:

1. **Tactical picture (shared).** Each activation rebuilds threat, support,
   cover and objective layers from the visibility-safe observation. LOS and
   cover come from an internal geometric model, so the TTS probe is kept for
   verification. Every decision area reads these layers.
2. **Candidate generation (rules-owned).**
   - The rules engine lists legal activations per ready operative: order, then
     an action sequence within APL.
   - Movement destinations come from TPS-style queries: generate, filter
     legality through the rules engine, then score.
   - This keeps the rules engine as the authority (ADR-0009).
3. **Utility scoring with exact dice.**
   - Target and weapon choice uses the exact damage distribution: P(incapacitate)
     and expected wounds, times target value.
   - Movement uses map-based considerations.
   - Dual-utility *ranks* hold overrides, such as "objective about to be lost"
     or "counteract window".
   - Weights live in the **team profile**, starting with Plague Marines.
4. **Activation choice.** Pick the operative whose best activation scores
   highest, adjusted by *urgency*: how much the value drops if the opponent
   activates first. This is the cheap stand-in for lookahead.
5. **Setup and doctrine.** A small HTN-style method table in the team profile
   breaks deployment and per-turning-point intent into role slots. Slots are
   filled by TPS queries plus team-level assignment (greedy or optimal
   matching), and the plan is redone after every human batch. Setup gets no
   search.
6. **Explanation record.** Every decision stores:
   - the chosen candidate
   - the top 2–3 alternatives
   - each consideration's contribution
   - the active doctrine method

   The announced plan turns this record into a natural-language sentence. An
   LLM may phrase it, but never chooses or changes the action.
7. **Optional search layer (later).** Add a portfolio-style shallow search or
   MCTS only after two prerequisites:
   - a copyable in-memory forward model exists
   - a benchmark shows enough play-outs fit in the time budget

   The search would cover only the top-K candidates from layers 3–4, use a
   utility-policy opponent model, outcome-bucketed chance nodes, and a hard
   time budget. The rule is the one Roelofs and Prismata used: heuristics
   generate the candidates, search arbitrates. Ship it only if it beats the
   utility-only AI in a self-play round robin, and keep the utility-only AI as
   a difficulty level.

**Why this fits.**

- **It meets every hard constraint.** It's pure Python and runs in
  milliseconds to seconds. It needs no training data. It's deterministic
  enough to test against the fake bridge. It never peeks at hidden state or
  future dice.
- **Every decision can be explained** from a stored score breakdown.
- **It matches what has worked in comparable games.** XCOM 2, Gears Tactics
  and Wesnoth ship utility and spatial-scoring hybrids. Scripted heuristic
  bots won the early Bot Bowls, and early MCTS bots lost.
- **Search is added only where it has measurably paid off**: for engaged units
  and activation choice, on top of heuristic candidates.
- **Kill Team's alternating activations already provide the decomposition**
  that tactics-game MCTS otherwise has to engineer, so the later search layer
  stays an incremental add-on.

**Rejected as the core.**

- GOAP: no adversary or chance model, and little to plan within APL 2–3.
- Pure MCTS: high cost in Python, weak explanations, poor at setup.
- Learned policies (RL or imitation): the training cost and data aren't
  available, and they're opaque. The AI and Wargaming review estimates
  "$250,000+ for a single training run of AlphaZero".

## Open questions for #7 and follow-ups

- **Python throughput.** How many forward-model steps per second can a pure
  Python model of Kill Team movement, LOS and attacks run? Make this a
  prototype or benchmark ticket before committing to layer 7.
- **Internal LOS model.** How faithful must the in-memory LOS/cover model be
  to the TTS probe? How are disagreements turned into an uncertainty stop
  rather than a silent override (hybrid game state)?
- **Hidden selections.** Does the target mission pack have secret selections
  (for example tac ops)? If so, which public prior is the AI allowed to use?
- **Fight resolution policy.** What policy should the AI assume for the human
  in fights (strike or block)?

## Sources not used or not verified

- **Frozen Synapse:** no primary source describing its AI opponent was found.
  It's excluded.
- **Total War:** the MCTS and GOAP details come from a secondary write-up. The
  primary talk (Gosling, Game AI Conference 2015) and Champandard's AiGameDev
  coverage weren't reachable.
- **Drefsante:** the description of the Bot Bowl IV/V winner as "scripted" comes
  only from press coverage
  ([Wargamer](https://www.wargamer.com/blood-bowl-3/ai-challenge)). The
  official pages name the winner but not the method.

## Primary sources

- [Kill Team Lite Rules (Games Workshop, PDF)](https://assets.warhammer-community.com/rules-downloads/kill-team/key-downloads/kill-team-lite-rules/killteam_keydownloads_literules_eng_02.10.24.pdf)
- Game AI Pro (free chapters, [gameaipro.com](http://www.gameaipro.com/)):
  - [Graham — An Introduction to Utility Theory](http://www.gameaipro.com/GameAIPro/GameAIPro_Chapter09_An_Introduction_to_Utility_Theory.pdf)
  - [Humphreys — Exploring HTN Planners through Example](http://www.gameaipro.com/GameAIPro/GameAIPro_Chapter12_Exploring_HTN_Planners_through_Example.pdf)
  - [van der Sterren — Hierarchical Plan-Space Planning for Multi-unit Combat Maneuvers](http://www.gameaipro.com/GameAIPro/GameAIPro_Chapter13_Hierarchical_Plan-Space_Planning_for_Multi-unit_Combat_Maneuvers.pdf)
  - [Jack — Tactical Position Selection](http://www.gameaipro.com/GameAIPro/GameAIPro_Chapter26_Tactical_Position_Selection.pdf)
  - [Dill — Dual-Utility Reasoning](http://www.gameaipro.com/GameAIPro2/GameAIPro2_Chapter03_Dual-Utility_Reasoning.pdf)
  - [Sturtevant — Monte Carlo Tree Search and Related Algorithms for Games](http://www.gameaipro.com/GameAIPro2/GameAIPro2_Chapter25_Monte_Carlo_Tree_Search_and_Related_Algorithms_for_Games.pdf)
  - [Lewis — Escaping the Grid: Infinite-Resolution Influence Mapping](http://www.gameaipro.com/GameAIPro2/GameAIPro2_Chapter29_Escaping_the_Grid_Infinite-Resolution_Influence_Mapping.pdf)
  - [Mark — Modular Tactical Influence Maps](http://www.gameaipro.com/GameAIPro2/GameAIPro2_Chapter30_Modular_Tactical_Influence_Maps.pdf)
  - [Dill — Spatial Reasoning for Strategic Decision Making](http://www.gameaipro.com/GameAIPro2/GameAIPro2_Chapter31_Spatial_Reasoning_for_Strategic_Decision_Making.pdf)
  - [Lewis — Choosing Effective Utility-Based Considerations](http://www.gameaipro.com/GameAIPro3/GameAIPro3_Chapter13_Choosing_Effective_Utility-Based_Considerations.pdf)
  - [Roelofs — Pitfalls and Solutions When Using MCTS for Strategy and Tactical Games](http://www.gameaipro.com/GameAIPro3/GameAIPro3_Chapter28_Pitfalls_and_Solutions_When_Using_Monte_Carlo_Tree_Search_for_Strategy_and_Tactical_Games.pdf)
  - [Churchill & Buro — Hierarchical Portfolio Search in Prismata](http://www.gameaipro.com/GameAIPro3/GameAIPro3_Chapter30_Hierarchical_Portfolio_Search_in_Prismata.pdf)
  - [Siemonsmeier — Simultaneous AI Actions in Gears Tactics (Online Edition 2021)](http://www.gameaipro.com/GameAIProOnlineEdition2021/GameAIProOnlineEdition2021_Chapter03_Gearing_the_Tactics_Genre_Simultaneous_AI_Actions_in_Gears_Tactics.pdf)
- Source code:
  - [XCOM 2 WotC Community Highlander — `XGAIBehavior.uc`](https://github.com/X2CommunityCore/X2WOTCCommunityHighlander/blob/master/X2WOTCCommunityHighlander/Src/XComGame/Classes/XGAIBehavior.uc)
  - [XCOM 2 WotC Community Highlander — `X2AIBTDefaultActions.uc`](https://github.com/X2CommunityCore/X2WOTCCommunityHighlander/blob/master/X2WOTCCommunityHighlander/Src/XComGame/Classes/X2AIBTDefaultActions.uc)
  - [Battle for Wesnoth — `src/ai/default/attack.cpp`](https://github.com/wesnoth/wesnoth/blob/master/src/ai/default/attack.cpp)
  - [Battle for Wesnoth wiki — RCA AI](https://wiki.wesnoth.org/RCA_AI)
  - [botbowl framework docs: MCTS tutorial](https://github.com/njustesen/botbowl/blob/main/docs/mcts.md)
  - Bot Bowl results:
    [I](https://github.com/njustesen/botbowl/blob/main/docs/bot-bowl-i.md),
    [II](https://github.com/njustesen/botbowl/blob/main/docs/bot-bowl-ii.md),
    [III](https://github.com/njustesen/botbowl/blob/main/docs/bot-bowl-iii.md),
    [IV](https://github.com/njustesen/botbowl/blob/main/docs/bot-bowl-iv.md),
    [V](https://github.com/njustesen/botbowl/blob/main/docs/bot-bowl-v.md)
- Papers and talks:
  - [Goodman, Risi & Lucas — AI and Wargaming (2020)](https://arxiv.org/abs/2009.08922)
  - [Justesen et al. — Blood Bowl: A New Board Game Challenge and Competition for AI (CoG 2019)](https://pure.itu.dk/en/publications/blood-bowl-a-new-board-game-challenge-and-competition-for-ai/)
  - [Justesen et al. — Playing Multi-Action Adversarial Games: Online Evolutionary Planning versus Tree Search (IEEE TCIAIG 2017)](https://pure.itu.dk/en/publications/playing-multi-action-adversarial-games-online-evolutionary-planni/)
  - [Pezzotti — MimicBot (2021)](https://arxiv.org/abs/2108.09478)
  - [Browne et al. — A Survey of Monte Carlo Tree Search Methods (2012)](https://doi.org/10.1109/TCIAIG.2012.2186810)
  - [Lanctot et al. — Monte Carlo \*-Minimax Search (IJCAI 2013)](https://arxiv.org/abs/1304.6057)
  - [Cowling, Powley & Whitehouse — Information Set MCTS (2012)](https://doi.org/10.1109/TCIAIG.2012.2200894)
  - [Orkin — Three States and a Plan: The AI of F.E.A.R. (GDC 2006)](https://pages.cs.wisc.edu/~dyer/cs540/handouts/gdc2006_orkin_jeff_fear.pdf)
  - [Verweij — A Hierarchically-Layered Multiplayer Bot System for a First-Person Shooter (Killzone 2, 2007)](https://www.guerrilla-games.com/media/News/Files/VUA07_Verweij_Hierarchically-Layered-MP-Bot_System.pdf)
  - [Mark & Dill — Improving AI Decision Modeling Through Utility Theory (GDC 2010)](https://gdcvault.com/play/1012410/Improving-AI-Decision-Modeling-Through)
- Secondary (used only where noted):
  - [Thompson — The AI of Total War, part 3 (Game Developer)](https://www.gamedeveloper.com/design/revolutionary-warfare-the-ai-of-total-war-part-3-)
