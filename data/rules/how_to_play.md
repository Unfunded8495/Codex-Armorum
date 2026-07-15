# How to Actually Play Warhammer 40,000

*A walkthrough and table companion for 11th Edition: from a blank table to the final score.*

The core rules explain every rule in isolation, but they never tell you what to physically do first, second and third on game day. This guide does. It is written for players who know the shape of the game but do not play every week: alongside the walkthrough, every section carries the details, timings and traps that occasional players forget between games. Every rule referenced here is 11th Edition and can be found in full in the Rules section; section numbers (like 07.02) match the core rules reference numbers used there. The Rules Insights page holds the full community articles this guide draws on.

---

## 1. What You Need

- **Two armies** of Citadel miniatures, one per player, built to an agreed points size (see below).
- **An army list** for each player: which units, which wargear, which enhancements. Build and validate yours in the Army Builder.
- **A table.** The mission's deployment map defines the battlefield dimensions and zones; matched play missions assume a standard-size battlefield with room for the deployment zones shown on the map.
- **Terrain**: ruins, containers, woods, crates, anything that blocks movement and sight. More is better than less; a bare table heavily favours shooting armies.
- **Dice** (a good handful of D6), a **tape measure** in inches, and something to mark objectives (the mission layout shows where they go).
- **A mission**, generated before you begin (from a mission deck or the Missions page).
- Optional but useful: tokens or dice to track Command Points, battle-shock and objective control. Battle-shock in particular persists across turns in 11th Edition, so tokens earn their keep.

---

## 2. Before Game Day: Muster Your Army

Missions instruct players to muster an army and state the total size those armies should be. The three standard battle sizes are:

| Battle size | Points limit | Detachment points | Enhancement limit | Duplicate datasheet limit |
|---|---|---|---|---|
| Incursion | 1,000 | 2 | 2 | 2 |
| Strike Force | 2,000 | 3 | 4 | 3 |
| Onslaught | 3,000 | 3 | 4 | 3 |

Strike Force (2,000 points) is the default for most games. In practice, mustering means:

1. **Pick an army faction.** Your units' faction abilities only apply if the army faction you selected matches a faction keyword on their datasheet (22.02). Your Warlord must share that faction keyword.
2. **Pick your detachment(s)** within the detachment points allowance. Each detachment brings its own rules, enhancements and stratagems.
3. **Add units** until you reach the points limit, respecting the duplicate limit (doubled for Battleline and Dedicated Transport datasheets) and any per-unit restrictions.
4. **Attach your characters.** For each Leader in your army, you select the bodyguard unit it will lead. This happens at muster, not on game day, and it is permanent: you cannot re-shuffle leaders between games in an event, and during the battle the attached unit stays a single unit even if the leader or every bodyguard model dies (19.01). A unit can hold one **Leader** and one **Support** character; Support characters must attach to a unit and can never deploy alone.
5. **Choose wargear and enhancements** (within the enhancement limit for the battle size). Each unit can carry at most one enhancement, picked after characters attach.

The Army Builder on this site enforces all of the above (points, tiers, detachment rules, leader eligibility, enhancement limits), so a list it accepts is a legal list.

**Worth remembering about attached units (19):** the unit shares every datasheet's keywords, but a rule that needs a keyword stops working once every model with that keyword is dead. Abilities work unit-wide while any model of the providing datasheet lives, so sniping the leader out with [Precision] attacks switches off the leader's buffs even though the unit fights on.

---

## 3. Game Day: Setting Up

Your mission card lists the exact setup sequence to follow; the steps below are the shape almost every matched play mission takes. The named steps (Muster Armies, Declare Battle Formations, Resolve Pre-battle Abilities, Begin the Battle) are the official pre-battle steps that rules refer to.

### 3.1 Generate the mission

Draw or pick, before anything is placed on the table:

- a **primary mission** (how you score most of your victory points),
- a **deployment map** (Hammer and Anvil, Crucible of Battle, Sweeping Engagement, Dawn of War, Tipping Point, Search and Destroy),
- a **mission layout** (where terrain and objectives go),
- and, if you both agree to use them, a **mission twist** (a battle-wide special rule such as Night Fighting or Ruinscape).

Secondary missions, if your mission pack uses them, are drawn as the game goes on; keep the deck handy. The Missions page on this site holds the current matched play pack (Chapter Approved) with every primary, secondary, deployment map, layout and twist, including the scoring text for each battle round.

### 3.2 Build the battlefield

Place terrain features on the table following the mission layout, or by agreement if you are freestyling (13.01). Each cluster of terrain (or the mat or base it sits on) defines a **terrain area**. Terrain features come in three categories (13.02):

- **Exposed** (craters, razorwire, debris): no real protection, no hindrance, but they can still grant cover to a unit not fully visible behind them.
- **Light** (barricades, low walls, statuary): can give the benefit of cover and makes the area obscuring, does not block movement.
- **Dense** (buildings, ruins, containers, woods): blocks sight and movement; these matter most. Only INFANTRY, BEASTS and SWARM models can move through them (others go around, or over parts under 2" tall).

If in doubt, err on the side of more dense terrain, and leave room around it for big models to move (the core rules explicitly recommend this).

The official Event Companion publishes the exact terrain area footprints used at Games Workshop events: four 6" x 4", two 10" x 2.5", four 6" x 2", four 7" x 11.5" and two 8" x 11.5" polygonal areas, with each feature designated light or dense. It also deliberately leaves space between a feature and the edge of its area so a line of models can stand on the area "from the outside": that gap is what makes toeing onto objectives possible. Copying that pattern gives you a table that plays the way the designers intended.

Terrain also decides who can see whom and how hard units are to hit. Four rules matter every turn:

- **Benefit of cover (13.08):** in 11th Edition, cover does not improve a save. Instead, it worsens the attacker's Ballistic Skill by 1, so the shooter needs a higher hit roll. A unit has the benefit of cover against a ranged attack if every model in it is either an INFANTRY, BEASTS or SWARM model within a terrain area, or not fully visible to the shooter because of intervening terrain or an obscuring terrain area. Two traps: it takes **every** model in the target unit to qualify (one model drifting into the open strips cover from the whole squad), and it is judged **per attacking model**, so half of an attacking unit may suffer the penalty while the other half does not, resolved as separate groups.
- **Hidden (13.09):** an INFANTRY, BEASTS or SWARM model sitting in a terrain area that contains light or dense terrain, whose unit did not make any ranged attacks this turn or last turn, is hidden (the printed core rules said dense only; the rules commentary widened it to light as well, which makes every area on the official layouts qualify). Enemies can only see a hidden model from within its **detection range**, 15" by default. You can be hidden on the very first turn. Shooting, including Fire Overwatch, breaks the effect for this turn and the next.
- **Gone to Ground (13.11):** a hidden model that is also not fully visible to the attacker because of intervening dense (Solid) terrain has its detection range cut by another 3", to 12". Detection range can never be modified below 9" or above 30".
- **Line of sight (13.10 to 13.11):** light and dense terrain areas are obscuring. If every line you could draw between two models crosses an obscuring terrain area that neither model is inside, they cannot see each other. But a model merely **within** an obscuring area (a toe inside is enough) ignores that area's obscuring rule, which is why fighting for the big central ruin matters so much. Dense terrain is also solid: you cannot draw line of sight through ground-floor openings such as windows, doors or gaps that are 3" or less above the ground, and models cannot end a move poking through them.

### 3.3 Place objectives

The deployment map shows several objective points. Each one should coincide with a terrain area; that whole terrain area **is** the objective, called a **terrain objective** (14.01). A model is within range of a terrain objective while it is within that terrain area. Mark the areas clearly. The official layouts label each objective as **Home** (in a deployment zone), **Expansion** (no man's land, offset toward one player) or **Central**; missions often pay the most for Central objectives because they are the most dangerous to hold.

### 3.4 Roll off, pick sides, deploy

This is the official pre-battle order from the Event Companion, the sequence used verbatim at Games Workshop events and the shape every matched play game should follow:

1. **Roll off** to determine Attacker and Defender (your mission states what each chooses; typically one picks the deployment zone, or at events you agree which battlefield edges match the layout card first).
2. **Declare Battle Formations.** Both players note down **secretly**, then reveal together: which units start embarked in which transports (18), and which units are in **strategic reserves** (20.01), including those using deployment abilities such as Deep Strike. Reserves are capped at 1,000 points at Strike Force (half your army at other sizes), in one shared pool. Aircraft must start in strategic reserves (23.01) and count against that cap.
3. **Deploy your armies.** Players alternate setting up one unit at a time, wholly within their own deployment zone, **starting with the Defender**. Setting up a TITANIC unit costs you your next set-up turn. When one player finishes, the other sets up all their remaining units.
4. **Redeploy units.** Rules that let you redeploy after both armies are set up resolve now, alternating, starting with the Attacker. A unit placed into strategic reserves by a redeploy does not count against the reserves points cap.
5. **Determine the first turn**: roll off, the winner takes it. The same player takes the first turn in every battle round (07.02).
6. **Resolve Pre-battle Rules.** Players alternate resolving pre-battle rules, starting with the player taking the first turn; Scout moves happen here (24.31). Scouts no longer work for units deployed outside your deployment zone.
7. **Begin the Battle.**

At the start of the battle, no objective is controlled by either player, and both players start with the CP their mission gives them.

**Playing at an event?** Warhammer Events do not use Deployment or Twist cards. Instead, when mustering you select one of the **Force Disposition** cards available to your detachment and record it on your roster; at the table you find your opponent's disposition symbol on your own card, and the primary mission listed under it is yours. Each pairing of primary missions has three fixed layouts (A, B and C). Those pairings and layouts are exactly the mission presets on the Missions page.

---

## 4. The Battle Round

The game is played in **battle rounds** (usually five; your mission says how many). Each battle round (07):

1. **Start of battle round** (resolve any "start of battle round" rules),
2. **Player turns**: the first player takes a full turn, then the second player takes a full turn,
3. **End of battle round** (resolve end-of-round rules, then check the mission for scoring).

Each player turn has seven parts (07.02): a Start of Turn step, five phases in order, and an End of Turn step. Every phase also has its own start and end steps, and rules that share a timing window resolve in a fixed order (01.03): the active player resolves all their mandatory rules, then their optional ones, and only then does the opposing player do the same. The opposing player therefore always gets the last word.

The five phases are the heart of the game:

### 4.1 Command Phase (08)

1. **Both players gain 1 CP** (yes, both, every turn).
2. **Battle-shock:** the active player makes a battle-shock roll for each of their units that is at or below half-strength, or already battle-shocked (08.03). At half-strength counts, not just below it, so even two-model units test. A failed unit stays battle-shocked and does not recover on its own: it keeps testing in later Command phases and only shakes it off when a battle-shock roll succeeds. While battle-shocked, a unit's models have their OC changed to "-" (an unmodifiable zero, so +1 OC buffs cannot rescue it), it cannot be targeted by its own player's stratagems, and it cannot start or finish actions (01.07). Insane Bravery (15.04) auto-passes one test per battle, but it targets the unit, and battle-shocked units cannot be targeted by their own stratagems, so it can never rescue a unit that is already shocked and trying to recover.
3. Resolve any command abilities your units have. This step comes **after** battle-shock, so abilities that return models to a unit will not save it from testing this phase.

**Easy to forget:** the End of Command Phase step has a dedicated mission-scoring sub-step that resolves after every other end-of-phase effect. Many primaries score here.

### 4.2 Movement Phase (09)

Move your units one at a time. Each unit picks one move type:

- **Remain Stationary** (some weapons and abilities reward this; note this really means stationary, not even a free pivot),
- **Normal Move**: up to its Move (M) characteristic,
- **Advance Move**: M plus a D6, but afterwards the unit can only shoot Assault weapons and cannot charge or start actions,
- **Fall-back Move**: leave engagement range of enemy models. This is modal (09.07). An **Ordered Retreat** (only if not battle-shocked) moves up to M and the unit cannot shoot, act or charge this turn. A **Desperate Escape** is forced if the unit is battle-shocked or must move through enemy models: every model in the unit makes a hazard roll, and the unit then takes a battle-shock test.

Models move in straight lines and pivots, measured part to part (03); pivoting around the centre is free, which effectively lengthens the reach of very large models. Units must end moves in **coherency** (03.03): every model within 2" of another model of the unit, and every model within 9" of every other model, so the whole unit fits a 9" circle. No more conga lines. Units cannot **end** a move within **engagement range** of enemy models, which is **2" horizontally and 5" vertically** (03.04), but standard moves may now pass through enemy engagement range freely on the way. Monsters and vehicles can even move through non-MONSTER, non-VEHICLE enemy models on a normal or advance move, so a ring of cheap infantry no longer traps them. FLY models can Take to the Skies during a move: pay 2" of movement to pass through all models and terrain and ignore vertical distance.

**Reinforcements arrive here.** There is no separate reinforcements step: units in strategic reserves or in transports are simply eligible for particular move types. Arriving from reserves is an **ingress move** (20.04): set up more than 8" from all enemy models, wholly within 6" of a battlefield edge, and outside the enemy deployment zone before battle round three. Deep Strike relaxes the edge and zone limits (anywhere on the table, still more than 8" away). Nothing arrives in battle round one, and anything still in strategic reserves at the end of round three is destroyed (20.01). A unit that makes an ingress move cannot move again until the next Charge phase: no arriving, shooting, then stepping back behind a wall.

**Transports (18):** a unit can embark if it ends a normal, advance or fall-back move with every model within 3" of the transport, but not if it was set up on the battlefield this turn, so a unit cannot disembark and re-embark in the same turn. Disembarking is a move type of its own with three modes: **Rapid Disembark** (after the transport made a normal or ingress move: out within 3", no charging this turn), **Tactical Disembark** (before the transport moves, or it stayed stationary: out within 3", then immediately make a normal or advance move), and **Combat Disembark** (only when nothing else is possible: out within 6", may be set up engaged with units engaging the transport, at the price of whole-unit hazard rolls and a battle-shock test). Passengers of a destroyed transport make an emergency disembark (18.05): within 6", unengaged, as close to the wreck as possible, hazard rolls for everyone, automatically battle-shocked, and no charging this turn.

**Easy to forget:** the end of your Movement phase is your opponent's window. Their Rapid Ingress and Fire Overwatch stratagems both trigger at the end of **your** Movement phase, so finish your moves knowing they may drop a unit in or shoot.

### 4.3 Shooting Phase (10)

Select each unit that is eligible to shoot, one at a time (10.02). A unit picks one shooting type (10.04 to 10.07):

- **Normal Shooting**: did not advance, unengaged, all ranged weapons.
- **Assault Shooting**: advanced this turn, unengaged, Assault weapons only.
- **Close-Quarters Shooting**: for engaged units. Monsters and vehicles can shoot any target this way (even units they are engaged with, though not with Blast weapons) at -1 to hit unless the weapon is Close-Quarters; the Heavy bonus never applies while engaged. Other engaged units can only fire Pistol or Close-Quarters weapons, at the units they are engaged with, without penalty.
- **Indirect Shooting**: unengaged, did not advance, lets Indirect Fire weapons target what they cannot see, at a stiff price: the target gets cover, hit rolls cannot be re-rolled, and only unmodified 6s hit unless the unit remained stationary and a friendly unit can see the target (then unmodified 1 to 3 still fails).

For each unit: select the weapons the models will use (04.01), select targets for all of them, then resolve. Targets must be visible, in range and unengaged (04.02), but the model that is visible and the model that is in range no longer need to be the same model. Range-dependent abilities like [Rapid Fire] and [Melta] check half range against the target unit at the Select Targets step, so resolving other weapons first cannot switch them off.

Before you resolve hits, check terrain: if the target has the benefit of cover, worsen your Ballistic Skill by 1 for those attacks (see 3.2), remembering the per-attacking-model check. A hidden unit cannot be selected as a target at all unless a model in your unit is within its detection range. And if any of your models sit on a terrain section more than 3" up, **Plunging Fire** gives those attacks +1 BS against ground-level targets, cancelling cover; TOWERING models get this automatically against visible ground targets within 12".

**Easy to forget:** shooting at an engaged MONSTER or VEHICLE is legal for everyone, at -1 to hit. And a unit that shoots cannot start an action this turn, and vice versa, so decide before pulling triggers which units you need for mission tasks.

### 4.4 Charge Phase (11)

Units that want to fight in melee must charge, and the order of operations matters. First, select a unit that is eligible to charge: within 12" of one or more enemy units, not engaged, and it did not advance or fall back this turn. **Then make a charge roll of 2D6**: that result is the maximum distance for the charge move (11.02). Only after rolling do you pick your targets: enemy units within 12" and within the rolled distance, measured point to point (11.04). A unit 10" away cannot be selected on a roll of 9, even though 9" of movement would reach its 2" engagement bubble. Once targets are legal you get about 2" of slack, since the charge only needs to end in engagement range.

The charge move itself has no base-to-base requirement. Each model that moves must end closer to a charge target, within 1" of one if it can, and engaged with one if it can. The unit must end engaged with **every** target it selected and no enemy unit it did not select; if it cannot, it does not move at all. You can also roll, dislike your options and simply decline to move: legal, and sometimes right. Charging pays off: every model in a unit that made a charge move has Fights First until the end of the turn. Charges out of Deep Strike still need a 9, since you set up more than 8" away.

**Easy to forget:** there is no Overwatch in the Charge phase in 11th Edition (it moved to the end of the Movement phase). Your opponent's counterplay here is Heroic Intervention at the end of the phase, so do not assume an untouched unit is safe just because your charges are done.

### 4.5 Fight Phase (12)

Both players act in this phase. It runs in three big steps:

1. **Pile In (12.02):** all pile-ins happen before any fighting. The active player moves every eligible unit (engaged, or made a charge move), then the opposing player does the same, often into whatever cage the active player just built. A pile-in is up to 3": an engaged unit must target all units it is engaged with, and each model ends closer to (and if possible engaged with) the closest target. Models already in base contact cannot pile in at all, which is exactly why basing enemy models on your pile-ins can pin their reply.
2. **Fight (12.04):** eligibility locks at the start of this step: a unit that was engaged then, or that charged, fights even if casualties pull it out of engagement (it makes an **overrun fight** with a bonus pile-in when activated, 12.06). Units fight one at a time. All **Fights First** units go first, players alternating, and the **active player picks first**; then all remaining eligible units, continuing the alternation. When a unit fights, only models within engagement range (2" horizontally, 5" vertically) swing, they use the same attack sequence as shooting, and they must use all of their attacks. You must fight with every unit that can.
3. **Consolidate (12.07):** both players move again, active player's units first, and the mode is dictated by the situation. **Ongoing** (still engaged): up to 3" toward the nearest engaged enemy. **Engaging** (unengaged but within 3" of an enemy): move to engage them, and a target that has not yet fought this phase immediately becomes eligible and fights right away. **Objective** (neither, but within 3" of an objective): up to 3" ending in range of it or closer to it, which on a terrain objective you already hold is effectively a free 3" shuffle.

**Easy to forget:** two of your units charging the same target is how chain wipes happen: the first wipes it, the second overruns 3" into fresh victims. Conversely, careful casualty allocation that leaves one enemy model alive within 2" of one of yours denies the overrun: only that one model swings back.

### The Attack Sequence (05): how every attack is resolved

Whether shooting or fighting, all attacks resolve the same way. Roll each step's dice together, then:

1. **Hit rolls:** one D6 per attack. Equal to or beat the weapon's BS (ranged) or WS (melee) to hit. Unmodified 1 always fails; unmodified 6 always hits and is a Critical Hit.
2. **Wound rolls:** one D6 per hit. Compare the weapon's Strength (S) to the target's Toughness (T):

   | S vs T | Needed |
   |---|---|
   | S at least double T | 2+ |
   | S greater than T | 3+ |
   | S equal to T | 4+ |
   | S less than T | 5+ |
   | S half T or less | 6+ |

   Unmodified 1 always fails; unmodified 6 is a Critical Wound.
3. **Save rolls:** the defender groups the models in the target unit (each character alone, then one group per identical W/Sv/InSv profile), declares the order attacks will be allocated (a non-character group with a wounded model first, characters never before non-characters, wounded characters before unwounded ones), then rolls one D6 per wounding hit and resolves them from the lowest roll up (05.03). Putting your worst-saved models early in the order soaks the low dice. Invulnerable saves are not optional: the roll is checked against the AP-modified save and the invulnerable save, and only fails if it beats neither. [Precision] hijacks this system: if any attacking model with a Precision weapon can see a character in the target unit, the attacker can make that character's group the current allocation group.
4. **Inflict damage:** each failed save inflicts the weapon's Damage (D) in lost wounds on a model in the current group. Feel No Pain rolls happen per wound lost, so a Damage 3 attack means three dice; roll variable damage when the failed save is allocated so you know how many. A model reduced to 0 wounds is destroyed, but excess damage from one attack does not spill over to the next model. Mortal wounds from [Devastating Wounds] pool and resolve at the end of each group of attacks.

**Modifiers (02.02)** apply in a strict order: anything that sets a value first (and if a value is set to 0 or "-", stop, nothing else applies), then multiplication, addition, division, subtraction, rounding up at the end. This is why [Melta] no longer beats half-damage effects, and why nothing rescues battle-shocked OC.

Keywords in square brackets on weapons ([Rapid Fire], [Lethal Hits], [Devastating Wounds] and friends) modify this sequence; each is defined in Core Abilities (24) and in the weapon tooltips throughout this site.

---

## 5. Objectives and Scoring: How You Actually Win

Kills alone do not win games; **victory points (VP) do**, and most VP come from standing on objectives.

- **Controlling an objective (14.02):** at the end of each phase and each turn, each player adds up the OC (Objective Control) characteristic of all their models within the objective's terrain area. Highest total controls it; a tie means nobody controls it (unless it is **secured**, 14.03, in which case the previous holder keeps it until actually beaten, even if the garrison is wiped out). Battle-shocked models contribute nothing, and a rule that asks whether a specific **unit** controls an objective needs that unit to have a model with OC 1 or more in range, so an OC 0 unit never satisfies it.
- **Primary mission:** your mission card says when and how you score, usually at the end of battle rounds or turns for holding objectives, with the exact timing on the card. The "End of Battle Round" and "End of Turn" steps exist precisely so you remember to check your mission then (07.03).
- **Secondary missions:** if your pack uses them, you score these alongside the primary. Before the battle each player secretly notes whether they will play **Fixed** or **Tactical** secondaries, then both reveal. Fixed: pick two Fixed-marked cards, display them face up; they stay active all battle and cannot be discarded. Tactical: shuffle the secondary deck and draw two face up at the start of each of your Command phases; once per battle, at the end of your Command phase, you can spend 1 CP to discard one active card and draw a replacement. At the end of **each player's turn** (the scorer first), check your active cards: score any you achieved (Tactical cards are then discarded), and if it is your turn you may discard one or more unwanted Tactical cards to gain 1 CP. "When Drawn" sections on cards only apply if you are playing Tactical.
- **Actions (16):** some missions and secondaries require units to perform battlefield tasks (raise banners, gather intel). A unit is eligible to start an action unless it is off the battlefield, an AIRCRAFT or FORTIFICATION, battle-shocked, OC 0 or "-", engaged (TITANIC units excepted), it advanced or fell back this turn, or it already started an action this turn (16.01). A unit that starts one cannot shoot or declare a charge for the rest of the turn (and any type of shooting likewise blocks starting an action), and moving before it completes fails it, so actions are a real tactical trade.
- **Hold from safety:** the Hidden rule (13.09) is the intended way to sit on objectives without being shot off them. A couple of models toed into the objective area, behind a solid wall for Gone to Ground, force the enemy to come to within 12 to 15" before they can even see you.

**The end of the battle and the caps.** The battle ends after the last battle round; being tabled does not end it early, so even with no models left, players play out their remaining turns (your opponent can still score, and so can any of your scoring already banked). Under the official scoring used at events, VP cap out at **45 from the primary** (up to 15 per battle round), **45 from secondaries** (up to 15 per battle round, and up to 20 per Fixed card), and **10 for bringing a Battle Ready painted army**, so 100 is a perfect score and paint is worth real points. Highest total wins; a tie is a draw.

**Reading mission cards.** The Event Companion settles the common wording disputes: a "cumulative" condition scores in addition to the normal condition, but "or" conditions never stack with it or each other; a unit "leaves the battlefield" if it is destroyed, embarks in a transport or is removed by a rule; an underlined "one" means exactly one, not one or more; and "up to XVP" is a hard ceiling, excess is ignored.

---

## 6. Command Points and Stratagems (15)

CP are your tactical currency. You gain 1 in every Command phase (including your opponent's turn) and spend them on **stratagems**: your detachment's own, plus the ten core stratagems every army has (15.02 to 15.12).

Two restrictions trip up every returning player: you cannot use the **same stratagem** more than once per phase, and you cannot target the **same unit** with more than one stratagem per phase. Command Re-roll is a stratagem, so re-rolling a unit's charge locks that unit out of every other stratagem for the phase. Some stratagems have a paid upgrade mode (+1 CP) you choose when using them.

- **Command Re-roll (1 CP):** re-roll one advance, charge, damage, hazard, hit, save, wound or number-of-attacks roll. One die of the roll, except charge rolls, which re-roll in full.
- **Epic Challenge (1 CP):** when your CHARACTER unit is selected to fight, one character's melee weapons gain [Precision] for the phase.
- **Insane Bravery (1 CP, once per battle):** auto-pass a battle-shock roll, used just before rolling. Cannot save a unit that is already battle-shocked.
- **Explosives (1 CP):** an unengaged EXPLOSIVES/GRENADES unit that did not advance picks a visible enemy unit within 8" and rolls six D6: each 4+ is a mortal wound.
- **Crushing Impact (1 CP):** a MONSTER or VEHICLE that just finished a charge move rolls dice equal to its Toughness against an engaged unit: each 5+ is a mortal wound to the enemy (max 6), each 1 a mortal wound to itself.
- **Rapid Ingress (1 CP):** at the end of your opponent's Movement phase, a unit in strategic reserves (not AIRCRAFT) makes an ingress move early. Not in the first battle round.
- **Fire Overwatch (1 CP):** at the end of your opponent's Movement phase, one of your unengaged units (not TITANIC) shoots using snap shooting: one visible target within 24", only unmodified 6s hit, no hit re-rolls.
- **Smokescreen (1 CP):** at the start of your opponent's Shooting phase, one of your SMOKE units gains the benefit of cover for the phase, and so does anything not fully visible behind its models.
- **Heroic Intervention (1 CP or 2 CP):** at the end of your opponent's Charge phase, one of your unengaged units resolves a charge of its own. The 1 CP mode (Leap to Defend) can only target units that charged this phase, but with no 6" cap any more. The 2 CP mode (Into the Fray) can target any enemy within 6", with the charge roll capped at 6.
- **Counter-offensive (2 CP):** in the Fight phase, just after an enemy unit fights, one of your eligible units gains Fights First and must be selected next.

Each stratagem states when it can be used, what it targets and what it costs. Counter-offensive is the only core stratagem that costs 2 CP; the rest are 1 CP. Spend CP; hoarding them wins nothing.

---

## 7. In Your Opponent's Turn

You are never just watching. The windows below are where the non-active player acts; missing them is one of the biggest gaps between occasional and regular players. Remember the sequencing rule (01.03): within any shared timing window, the active player resolves their rules first, so as the opposing player you always get the final say.

| When | You can |
|---|---|
| Their Command phase | You gain 1 CP too (08.02). |
| During their Movement phase | Nothing reactive: Overwatch is no longer triggered per move, so wait. |
| End of their Movement phase | **Rapid Ingress** a reserves unit in; **Fire Overwatch** with an unengaged unit (snap shooting). |
| Start of their Shooting phase | **Smokescreen** a SMOKE unit about to be shot. |
| While they shoot | You choose the save-group allocation order; your invulnerable saves and Feel No Pain apply automatically. |
| End of their Charge phase | **Heroic Intervention**: counter-charge a unit that charged (1 CP), or anything within 6" (2 CP). |
| Their Fight phase | Your engaged units pile in (after theirs), fight in the alternating sequence, and consolidate. **Counter-offensive** (2 CP) jumps one of your units up the order; **Epic Challenge** works when your character unit is selected to fight. |
| End of their turn | Scoring is checked per your mission; their aircraft return to reserves. |

One stratagem per unit per phase applies across all of this, and battle-shocked units cannot be targeted by your stratagems at all. Also remember your own units' "once per turn" abilities: many detachment rules trigger in either player's turn.

---

## 8. Rules People Get Wrong

Every entry here is a genuine table dispute the community articles keep having to settle. Rule numbers link to the full text; the Rules Insights page has the long-form explanations.

1. **Cover is a worse hit roll, not a better save (13.08).** It needs every model in the target unit to qualify, and it is checked per attacking model, so an attacking unit can be split into penalised and unpenalised groups.
2. **Roll the charge first, pick targets second (11.02, 11.04).** And targets must be within the distance rolled, measured point to point: a unit 10" away is not a legal target on a 9, even though the move would reach engagement range.
3. **Charges do not need base contact (11.04).** End closer, within 1" if possible, engaged if possible. Staying off base contact is often correct, because models in base contact cannot pile in next phase (12.02).
4. **Command Re-roll locks the unit (15.01).** One stratagem per unit per phase, and the re-roll counts. Re-rolling a charge means no Epic Challenge, no detachment stratagem, nothing else on that unit this phase.
5. **Invulnerable saves are not optional (05.03).** The roll is checked against both saves; you cannot deliberately fail to let a unit die on your terms.
6. **Battle-shock tests at half strength, and recovery is not automatic (08.03).** Already-shocked units keep testing every Command phase, and Insane Bravery cannot be used on them because shocked units cannot be targeted by their own stratagems.
7. **Fight eligibility locks at the start of the Fight step (12.04).** Killing every model engaged with an enemy unit does not deny its fight; it just fights as an overrun fight with a bonus pile-in (12.06). The real counterplay is leaving exactly one model alive within 2".
8. **The active player picks the first Fights First unit (12.04).** Charging a Fights First monster is no longer automatically fatal; your charging units have Fights First too, and you activate first.
9. **Modifiers have a fixed order (02.02):** set values first (a 0 or "-" stops everything), then multiply, add, divide, subtract. [Melta] no longer beats half-damage effects, and no +1 OC banner rescues a battle-shocked unit.
10. **Arriving from reserves ends your movement for the turn (20.04).** An ingress move (Deep Strike included) means no further moves until your next Charge phase: no arrive-shoot-scoot, and reserves also cannot arrive in round one and die in reserves after round three (20.01).
11. **You can move through enemy engagement range (03.04)**, you just cannot end there. And coherency now caps a unit inside a 9" circle (03.03), so the conga line is dead.
12. **Hidden breaks on shooting this turn or last (13.09)**, works in light terrain areas as well as dense (rules commentary), applies per model, and works on turn one. Fire Overwatch counts as shooting and breaks it.
13. **Overwatch happens at the end of the Movement phase (15.08), not during charges.** In the Charge phase your counterplay is Heroic Intervention (15.11) at the end of the phase.
14. **Disembarking uses the unit's move, and no re-embarking after being set up (18.02).** A unit that got out this turn cannot get back in; a Tactical Disembark moves before the transport does, with the hull still in place.
15. **[Rapid Fire] and [Melta] check half range at the Select Targets step (04.02)**, against the target unit, not against the model you happen to see, and resolving other weapons first cannot turn them off.

---

## 9. Your First Game (or First in a While)

1. Both players build a 1,000 point (Incursion) list in the Army Builder.
2. Pick one primary mission, one deployment map and one layout from the Missions page. Skip twists and secondaries the first time.
3. Set up terrain and objectives per the layout, roll off, deploy, roll for first turn.
4. Play all five battle rounds with the phase list in front of you. Expect the first game to be slow; by round three the phase rhythm (Command, Move, Shoot, Charge, Fight) becomes automatic.
5. Score primaries at the timing printed on the mission card, and total VP at the end.

Coming back after a break? The five minutes best spent before the game: re-read chapter 7 (your opponent's turn windows), chapter 8 (the misplays), and your own detachment rules and stratagems. Most rust shows up as missed windows, not forgotten fundamentals.

Common first-game mistakes to avoid: forgetting both players gain CP in every Command phase, forgetting battle-shock tests for half-strength units, treating cover as a better save instead of a worse hit roll for the shooter, forgetting to roll the charge before picking targets, and leaving objectives bare because everything went hunting kills.

---

## 10. Quick Reference

**Turn order:** Start of Turn, Command, Movement, Shooting, Charge, Fight, End of Turn.

**Attack sequence:** Hit, Wound, Save, Inflict Damage.

**Your turn, phase by phase:**

- **Command:** both gain 1 CP; battle-shock rolls (at or below half strength, plus already-shocked units); command abilities; mission scoring sub-step at the end.
- **Movement:** move or stay; reserves ingress (round two onwards); embark/disembark; end of phase is the enemy's Rapid Ingress and Fire Overwatch window.
- **Shooting:** pick shooting type per unit; targets all selected before resolving; check cover, hidden and plunging fire; shooting blocks actions.
- **Charge:** eligible within 12"; roll 2D6, then pick targets within the roll; chargers gain Fights First; enemy Heroic Intervention window at the end.
- **Fight:** all pile-ins (you first), then alternating fights (Fights First first, you pick first), then consolidations.

| Distance | Value |
|---|---|
| Engagement range | 2" horizontal, 5" vertical |
| Coherency | 2" to a neighbour, unit within a 9" circle |
| Charge declaration range | 12" |
| Charge move | 2D6" maximum |
| Pile-in / consolidation move | 3" |
| Advance bonus | +D6" |
| Ingress (reserves arrival) | more than 8" from enemies, within 6" of an edge |
| Deep Strike | more than 8" from enemies, anywhere |
| Detection range (a hidden unit) | 15", or 12" gone to ground |
| Snap shooting (Overwatch) target | within 24" |
| Heroic Intervention | within 12" (6" for Into the Fray) |
| Plunging Fire height | more than 3" up |

**Cover:** the benefit of cover worsens the shooter's Ballistic Skill by 1; it does not improve the target's save.

**Victory point caps (official event scoring):** primary 45 (up to 15 per round), secondaries 45 (up to 15 per round, 20 per Fixed card), Battle Ready paint 10. Perfect score 100.

**Stratagem windows in your opponent's turn:** Rapid Ingress and Fire Overwatch at the end of their Movement phase; Smokescreen at the start of their Shooting phase; Heroic Intervention at the end of their Charge phase; Counter-offensive after an enemy unit fights.

**Where to find things on this site:**

- **Rules**: the full 11th Edition core rules, searchable, with diagrams and commentary.
- **Rules Insights**: the full community deep-dive articles behind this guide.
- **Missions**: the current matched play pack: primaries, secondaries, deployment maps, layouts, twists and their scoring text.
- **Army Builder**: build legal lists with live points, detachment and enhancement enforcement.
- **Arsenal / Loadouts**: datasheets, weapon profiles and wargear options for everything you own.
- **Collection**: what you own and how painted it is, so you know what you can actually field.
