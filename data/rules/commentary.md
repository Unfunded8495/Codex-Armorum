# Commentary & Tactical Insights

Curated from community rules articles supplied by the user (11th Edition Rules
Deep Dive series, Ruleshammer and Hammer of Math). Parsed by
scripts/build_rules.py and injected into the /rules page as visually distinct
commentary blocks - this is insight and opinion, NOT official rules text.
The full articles live on /rules/insights (data/rules/insights/), and the
build links each entry's source name to its article: keep the source field
matching an article title or an alias in CMT_SOURCE_ALIASES, or the build
will warn.

Entry format:

    ## @<target> | <title> | <source>

where <target> is a rule ref (11.02), a section id (s13), or an anchor id
(appendix-destroyed). Body is markdown; bold terms, [ABILITY] tags and
(NN.NN) refs are cross-linked exactly like the official text.

---

## @01.03 | The opposing player gets the final say | Rules Deep Dive: Core Concepts

If it is your turn you are the **active player**, but if you are mid-move, or **selected to shoot** or **fight** during your opponent's turn, you temporarily become the active player until that resolves. When rules share identical timing (e.g. "at the end of the Movement phase"), the active player resolves all their mandatory rules, then all their optional ones - and *then* the opposing player does the same. The opposing player therefore usually has the last word on any given trigger, which lets them respond effectively; in 10th Edition the active player could neutralise combos simply by declaring a convenient order. Anything newly triggered while resolving waits until all pre-existing rules have finished.

## @02.02 | Modifier order of operations | Rules Deep Dive: Core Concepts

The extended rules pin down how multiple modifiers apply to a characteristic: first anything that **sets** a value (if this makes it 0 or '-', stop - nothing else applies), then multiplication, addition, division, subtraction, rounding fractions up at the end. Three common consequences:

- "Damage becomes 0" effects are no longer partially bypassed by +D effects.
- Half-damage effects are no longer bypassed by [MELTA] - you add first, then halve (and the old edge case where -1D beat half-damage against a D1+1 weapon is gone).
- +1 OC buffs no longer rescue a **battle-shocked** unit: OC is set to '-', which cannot be modified.

Detection range (Hidden) and Lone Operative range can never be modified better than 9" or worse than 30".

## @intro | Army construction changes (app rules) | Rules Deep Dive: Core Concepts

Army building lives in the extended app rules, not the printed book. The familiar skeleton remains (Army Faction, same points limits, three of each datasheet, doubled for Battleline and Dedicated Transports), with notable changes:

- Instead of one Detachment, you have a pool of Detachment Points - three at 2000pts - so you can field more than one.
- **Leaders** attach during army construction (Muster Armies), not pre-battle, so you cannot flex them between units game to game.
- Some characters are now **Support** rather than **Leaders**: identical mechanics, but they *must* join a unit. Each unit can take one Leader *and* one Support, centralising the old "double attachment" special rules.
- Each unit may take only one **enhancement**, picked after attaching characters. Some enhancements are Upgrades, which can go on non-character units up to three times (paying each time) while consuming a single enhancement pick.
- Your Warlord must share your Army Faction keyword.

## @s07 | Explicit start/end steps everywhere | Rules Deep Dive: Core Concepts

Every phase and turn now has defined Start of Phase and End of Phase steps, plus a defined scoring sub-step. Day to day this changes little, but timing wording can now be precise, and expect future publications to reference these sub-steps by name and number to fix race conditions.

## @06.03 | Hazard rolls reach further than hot plasma | Rules Deep Dive: Core Concepts

**Hazard rolls** generalise what used to be the Hazardous test: [HAZARDOUS] weapons, desperate escapes and emergency disembarks all force them. Rules that interact with hazard rolls therefore have much more breadth than "your plasma got hot" - and desperate escapes are slightly less lethal than their 10th Edition equivalents (though they now carry other drawbacks).

## @05.03 | Invulnerable saves are no longer optional | Rules Deep Dive: Core Concepts

An **invulnerable saving throw** is still an unmodifiable alternative to your normal save, but you no longer *choose* which to use. In 10th Edition it was occasionally right to take the worse save on purpose (to let a unit die on your terms); now the roll is simply checked against both and damage is inflicted only if it fails the better one.

## @05.03 | How save groups work | Ruleshammer: Save Groups, Precision & FNP

Fast-rolling saves finally has codified structure. Models divide into one group per **CHARACTER** model plus one group for each distinct combination of W, Sv and invulnerable save. You must declare the allocation order before rolling, respecting: a non-CHARACTER group containing a wounded model goes first; no CHARACTER group may come before a non-CHARACTER group; and wounded CHARACTER groups come before unwounded ones. Note the subtlety: a wounded *character* group does not jump the queue ahead of non-character groups. The point of all this structure is that other rules (notably [PRECISION]) can now leverage it.

## @s08 | Command phase overview | Rules Deep Dive: Command Phase

Morale is more fragile in 11th Edition and battle-shock will have far more impact on your games - stock up on tokens for tracking it. Also note the Command Abilities step comes *after* Battle-shock, so effects that return models to units resolve after morale has already been evaluated; units leaning on respawn effects are more brittle (and if the respawn is a stratagem and the unit failed its test, you are out of luck entirely - battle-shocked units can't be targeted by stratagems).

## @08.05 | Scoring settles last | Rules Deep Dive: Command Phase

The End of the Command Phase step has a dedicated mission-scoring sub-step that always happens after every other end-of-phase effect. Scoring is therefore evaluated on the final board state, after all ability dust has settled.

## @08.03 | Battle-shock is easier to fail and worse | Rules Deep Dive: Command Phase

Getting battle-shocked is both easier and nastier than in 10th Edition:

- You test at **half-strength**, not just below it - two-model units and 4W solo models are no longer effectively immune.
- OC becomes '-' (an unmodifiable zero), so banner-style +1 OC effects can't salvage it. Battle-shocked units also can't be targeted by your stratagems and fail any **actions**.
- No more automatic recovery: a unit that starts the phase battle-shocked must pass a fresh Leadership test to shake it off, and with most Ld values at 6-8 that is never certain.
- Insane Bravery (15.04) can auto-pass a test once per battle, but cannot be used on a unit that is *already* battle-shocked and trying to recover.

Consequences: anything that inflicts battle-shock in a radius (or forces tests out of sequence) rises sharply in value, as do effects that remove it. It's also a real transport nerf - an emergency disembark still auto-shocks the passengers, who may now stay shocked through your next scoring window.

## @03.03 | The conga line is dead | Rules Deep Dive: Movement

Coherency now demands every model within 2" of another model *and* every model within 9" of every other model - effectively, every base must touch a single 9" diameter circle. Stringing a big unit across the table is gone, hordes cover less ground, and fully screening a table edge is much harder (especially combined with the 8" ingress distance). For mid-sized melee units there's some upside: you can deploy models pushed out in several directions to keep charge angles open.

## @03.04 | 2" engagement range changes the geometry | Rules Deep Dive: Movement

Engagement range is now 2" horizontally (still 5" vertically), and there is no longer any restriction on *passing through* enemy engagement range with standard move types as long as you end outside it. Players used to eyeballing 1" will need recalibrating: a small melee unit can now zone a surprising amount of space in front of an objective, which makes suicide-melee threats genuinely awkward for shooting armies - you cannot simply walk onto the objective through their engagement bubble, so you must shoot them down to a remnant you can safely charge. Move-after-shooting abilities gain value for exactly this reason.

## @03.01 | Per-model movement is optional - mostly | Rules Deep Dive: Movement

For any move with a **maximum distance** you may move only some models in the unit - useful when a charge or pile-in would drag a model somewhere awkward. But watch the trap: 'While Moving' conditions bind each model *as it moves*, and **coherency** is only checked at the After Moving step - if the unit ends out of coherency, the *entire move* is undone. You cannot use the threat of breaking coherency to dodge a mandatory While Moving obligation: either move the other models to restore coherency, or the whole unit stays put.

## @03.01 | Pivots are free | Rules Deep Dive: Movement

All movement is a series of straight lines and pivots, and pivoting (rotating around the base's centre) costs no movement. On very large models a free pivot can add 1-2" of effective reach if they start wide-side-on - remember this both when attacking with them and when trying to stay out of their threat range. Models with a base may move through any gap the *base* fits through; overhanging tentacles and chainswords don't count.

## @s09 | No reinforcements step, and Overwatch moved | Rules Deep Dive: Movement

There is no separate Reinforcements step: at the start of your Movement phase every unit - including those in **strategic reserves** or embarked - is eligible to move, and where it is determines which move types it can take. Reserves units may only Remain Stationary or make an **ingress move**, resolved at any point in the phase (occasionally relevant if a movement buff aura is waiting in the wings). 10th Edition rules that referenced "the Reinforcements step" now resolve in the Move Units step. Also: Fire Overwatch now triggers in the *End of the Movement phase* step, not as a reaction to each move - no more asking "any overwatch?" after every unit, and no sequencing games to bait it out.

## @09.04 | Remaining stationary means stationary | Rules Deep Dive: Movement

"Doing nothing" includes no pivoting (pivots are free *during a move*, but they are still moving), and it does not trigger "ends a move" effects. Units in reserves or transports that stay put are treated as having Remained Stationary.

## @09.07 | Ordered retreat vs desperate escape | Rules Deep Dive: Movement

Falling back is now modal. An Ordered Retreat is the clean exit - available only if the unit is not **battle-shocked** - after which the unit can't shoot, act, or charge. If the unit is battle-shocked, or needs to move *through* enemy models to get out, it must take a Desperate Escape instead: every model in the unit makes a **hazard roll** (not just the ones squeezing past), and the unit then takes a battle-shock test if not already shocked. Compared to 10th Edition this is less lethal per dice to Monsters, Vehicles and multi-wound infantry, but the whole-unit hazard rolls and the shock test make being surrounded genuinely scary again - dust off the tri-point.

## @21.03 | FLY is a big-model buff now | Rules Deep Dive: Movement

The **FLY** keyword now does nothing at baseline - not even moving over enemy models. Instead, when making a normal, advance, fall-back or charge move a flyer can Take to the Skies: subtract 2" from its maximum distance, and for that move it passes freely through all enemy models and all terrain, ignoring vertical distance entirely. That's a modest downgrade for infantry (who could already slip through walls and now pay 2" to hop models) and a *massive* boost for Monsters, Vehicles and Mounted units, which can now pop out from behind big terrain at speed.

## @20.04 | Ingress: 8", and no moving afterwards | Rules Deep Dive: Movement

The default ingress is set up more than 8" from enemies (not 9"), wholly within 6" of a battlefield edge, and outside the enemy deployment zone before battle round three; **Deep Strike** simply relaxes the edge/zone restrictions. The big change: a unit that makes an ingress move is not eligible to make *any* further move until the next Charge phase - no more arriving, shooting, then scooting behind a wall with a post-shooting move. Newly written teleport-style abilities also work through ingress moves (remove, place in reserves, ingress immediately).

## @20.01 | One reserves pool, hard deadlines | Rules Deep Dive: Movement

There is now a single reserves limit (1000pts at Strike Force, or half your army) with no separate Deep Strike allocation. Core rules also bake in the timing: nothing arrives before battle round two unless stated, and anything that started the game in strategic reserves and hasn't arrived by the end of round three is destroyed (embarked passengers of an arrived transport are safe). Units placed into reserves *during* the battle are "repositioned units" and are exempt from the round-three deadline.

## @18.02 | No more fire-and-fade re-embarking | Rules Deep Dive: Movement

Embarking still requires ending a normal, advance or fall-back move with every model within 3" of the transport - but a unit that was *set up* on the battlefield this turn cannot embark. Since disembarking is a set-up, hop-out-shoot-hop-in tricks are dead as a core rule rather than being patched stratagem by stratagem.

## @18.04 | The three disembark modes | Rules Deep Dive: Movement

Disembarking is now a modal move type, and it consumes the unit's move for the turn:

- **Rapid Disembark** - after the transport made a normal or ingress move: set up wholly within 3", no charging this turn. After an ingress, the passengers must also obey every set-up restriction the transport had (you can no longer sneak onto spots the transport's own arrival conditions would forbid).
- **Tactical Disembark** - before the transport moves, or if it Remained Stationary: set up within 3", then *immediately* make a normal or advance move. Because the move happens with the transport still in place, the unit can never end up occupying the transport's original footprint - plan your staging accordingly.
- **Combat Disembark** - only if neither of the above is possible (usually because enemy engagement range smothers the hull): set up wholly within 6", allowed to be engaged with units already engaged with the transport, at the price of whole-unit **hazard rolls** and a battle-shock test.

Models with bases wider than 3" only need to be within 1" of the transport on the two 3" disembark modes - a smidge of extra reach for the likes of Ghazghkull.

## @18.05 | Emergency disembarks can be denied | Rules Deep Dive: Movement

Passengers of a destroyed transport set up wholly within 6", unengaged, *as close to the transport as possible* - enough slack to escape 2" engagement bubbles in most cases, but the reviewers suspect two enemy units cooperating around a transport (oval bike bases especially) can zone out every legal spot, destroying the passengers outright. Even a successful escape hurts: hazard rolls for everyone, and automatic battle-shock that may persist through your next Command phase.

## @11.02 | Roll first, pick targets second | Ruleshammer: Charge Phase

Two changes reshape charge declaration. First, you no longer nominate targets when declaring - you declare, roll 2D6, and *then* pick targets. Second, targets must be within the distance you rolled, measured point-to-point: a unit 10" away cannot be selected on a 9" roll even though 9" of movement would reach its 2" engagement bubble. In practice the 2" engagement range gives you ~2" of slack once a target is legal, so charges are generally easier - but a double 1 is now always a failure (you can never start within 2"), and charges out of Deep Strike still need a 9 (set up >8" away). Rolling and then declining to move is perfectly legal; there's no obligation to execute a charge you don't like. Remember eligibility runs through more than the printed list - e.g. an emergency disembark (18.05) strips charge eligibility for the turn, so you still can't wreck your own transport to launch a charge.

## @11.04 | No base-to-base requirement | Ruleshammer: Charge Phase

A persistent misreading: you are **not** required to reach base contact. Each moving model must end closer to a charge target, must end within 1" of one if it can, and must end **engaged** with one if it can - that's the full priority list. Staying off base contact is often *correct*, because models in base contact cannot make pile-in moves next phase. After moving, the unit must be engaged with every charge target and no other enemy units, and each model gains **Fights First** for the turn. Making the charge move at all is optional - but note that merely declaring a charge doesn't make you eligible to fight; you need to be engaged or to have actually made a charge move. And with 2" engagement, hiding an inch behind a wall no longer protects you from a monster swinging through it.

## @r15-11 | Heroic Intervention got scary | Rules Deep Dive: Charge & Fight

Now resolved at the end of the phase, and considerably buffed. The 1CP mode (Leap to Defend) still only counter-charges units that charged this phase, but the old 6" cap is gone - any target within 12" and your roll is fair game, and if several enemies ended charges nearby you can tag more than one. The +1CP mode (Into the Fray) can charge *any* enemy units within 6" but treats charge rolls above 6 as 6 - so parking a cheap unit "innocently" on an objective in front of a melee monster is no longer safe if your opponent has CP to spare.

## @12.02 | One shared pile-in step | Rules Deep Dive: Charge & Fight

All pile-ins happen together at the top of the phase: the active player moves every eligible unit (engaged, or made a charge move), then the opposing player does - often into whatever cage the active player just built. Models already in base contact cannot pile in, so the active player often *wants* to base enemy models during their pile-ins precisely to pin the reply. If a unit is engaged it must select *all* units it's engaged with as pile-in targets (each model ends closer to, and if possible engaged with, the *closest* target); an unengaged unit instead picks freely among units within 5" with no closest-target requirement, letting it concentrate on one victim.

## @12.04 | Fight eligibility locks in - and Fights First flipped | Rules Deep Dive: Charge & Fight

Units that start the Fight step eligible stay eligible even if casualties pull them out of engagement - they'll simply resolve an **overrun fight** (with its bonus pile-in) when activated. The counterplay is casualty allocation: leave exactly one enemy model alive within 2" of one of yours and the unit gets no extra pile-in - only that one model swings. Which models attack is purely the 2" engagement check, so huge-based models can't fight "through" a friend that based the enemy.

Selection order is the bigger shake-up: the *active player* picks the first **Fights First** unit (charging units all have it), alternating from there, and the alternation carries straight into normal fights. Charging a Fights-First deathstar is no longer a death sentence, and if you charged nothing you can even spend your first pick on a normal unit to bail it out early.

## @12.06 | Overrun fights enable chain wipes | Rules Deep Dive: Charge & Fight

If a unit is selected to fight while unengaged (or became engaged only after the step started), it makes an extra pile-in move before attacking. Two melee threats charged into the same target means: first unit wipes it, second unit overruns 3" (or 6" with the right ability) into fresh victims. Berzerker-style armies will punish anyone who hasn't adjusted to playing around this.

## @12.08 | Consolidation can start new fights | Rules Deep Dive: Charge & Fight

Consolidation is modal: **Ongoing** (engaged - every engaged unit becomes a target, non-base-contact models move up to 3" toward the nearest), **Engaging** (unengaged but close to an enemy - move to engage them, and any target not yet selected to fight this phase immediately becomes eligible and fights *right now*, potentially as an overrun fight), or **Objective** (neither applies but you're within 3" of an objective - each model moves up to 3", ending in range of it or closer to it; on a terrain objective you are already inside, this is effectively a free 3" shuffle, great for tucking behind a wall or getting **Hidden** online). Sequencing nuance: if the active player's engaging consolidation drags fresh opposing units into combat, those units still get their own consolidation later in the step - but the reverse is not true, as the active player's window has already passed.

## @s13 | Terrain is the objective now | Rules Deep Dive: Terrain & Objectives

11th Edition centres terrain completely: key **terrain areas** *are* the objectives by default, and terrain protects through three distinct mechanisms - cover (13.08), blocked visibility (13.10) and the new Hidden state (13.09). Understand the split between the physical **terrain feature** and the **terrain area** it sits in: the area boundary decides who is "within" for rules purposes and carries the visibility rules, while the physical features govern movement and true line of sight. An area can mix features of different categories - light infantry may dash through the middle while tanks wiggle around.

## @13.08 | Cover is -1 BS, judged per attacking model | Rules Deep Dive: Terrain & Objectives

Two things to internalise. Cover now imposes -1 BS on the attacker rather than buffing the save - and it's determined per *attacking model*, so a unit half in line-of-cover and half with clean sight splits its attacks into separately resolved groups. Defensively it's all-or-nothing per target: **every** model in the target unit must qualify, so one model drifting fully into the open strips cover from the whole squad (in 10th you at least kept saves on the covered models). Expect units to have cover less often, and AP-1 weapons to matter much more.

## @13.08 | The maths of -1 BS | Hammer of Math: Benefit of Cover

How much -1 BS is worth depends entirely on the starting characteristic: 3+ → 4+ is a 25% accuracy loss, 4+ → 5+ is 33%, 5+ → 6+ is 50%. Against a 5+ save target, old +1-save cover and new -1 BS cover feel nearly identical (5.93 vs 5.56 expected kills in the worked Intercessor example); against 4+ saves they're *exactly* equal. Two structural effects tilt the field:

- Hit rolls have a floor (a 6 always hits) while saves can be modified into impossibility - so AP keeps full value where hit penalties saturate.
- Invulnerable saves ignore cover entirely, so armies living on invulns (Daemons) treat the new cover rules as a flat upgrade.

Net winners: high-volume AP-1 platforms (heavy bolters, autocannons - especially with [SUSTAINED HITS], which offsets the penalty) and invuln-heavy armies. Net losers: low-volume "value" weapons like lascannons and multi-meltas, which get more volatile and comparatively weaker, more so on BS4+ platforms.

## @13.09 | Playing the Hidden game | Ruleshammer: Hidden & Gone to Ground

The checklist: be **INFANTRY/BEASTS/SWARM**, be within a terrain area containing at least one light *or* dense feature (the app rules widened this - the printed book said dense only, and on the official layouts every single area now qualifies), and don't have made ranged attacks this turn or last. You can be Hidden on turn one - the rules commentary confirms "didn't happen last turn" conditions are true when there was no last turn. While hidden, a model is only visible inside its detection range (15" by default, modifiable but never below 9" or above 30").

Practical notes: it's per *model* - if any non-hidden model in the unit is visible and in range, the unit can be targeted normally and Hidden bought you nothing. It doesn't change line of sight otherwise; behind a wall you're still just not visible. Firing **Overwatch** breaks it. Tactically, Hidden is the premier way to sit on objectives: step a couple of models onto the far side of the objective area, ideally behind something Solid, and enemies must close to 12-15" to even see you. It pairs beautifully with Scout infantry and with Infiltrators-style 12" arrival denial.

## @13.11 | Gone to Ground: the extra 3" | Ruleshammer: Hidden & Gone to Ground

An app-rules addition layered on Hidden: if a hidden model is *not fully visible* to the attacker because of intervening **Solid** terrain (i.e. any dense feature), and its unit hasn't made ranged attacks this or last turn, its detection range drops by 3" to 12". Unlike Hidden it isn't a global state - it's judged per attacking model and sightline. Light features never grant it (they aren't Solid), and units with "shoot and stay hidden" abilities explicitly don't get it. Those 3" matter more than they sound: on the official layouts, plenty of firing positions can see the whole of a neighbouring objective at 15" but not at 12", and stacking a further reduction toward the 9" floor makes a unit genuinely hard to dig out.

## @13.10 | Obscuring only needs a toe inside | Rules Deep Dive: Terrain & Objectives

Areas with light or dense features block visibility drawn across them when neither model is inside - but a firing model merely *within* the area (not wholly within) ignores the rule. That opens tables up dramatically for big shooting pieces: on many official layouts a single large central ruin transforms sightlines for whoever touches it. Expect sacrificial chaff (with their 2" engagement bubbles) to be spent purely on denying enemy models entry to the areas that unlock the key firing lanes.

## @22.05 | Plunging fire at 3", Towering gets it free | Rules Deep Dive: Special Unit Types

The height threshold is now a terrain section 3" or more in height (down from 6" in 10th), so elevated positions will actually come up in real games - +1 BS neatly cancels the target's cover, or boosts lethality in the open. Related: the **TOWERING** keyword no longer changes how such models see through terrain; instead a Towering model shooting visible ground-level targets within 12" automatically benefits from Plunging Fire. Aggressive Knight armies hit noticeably harder up close.

## @14.02 | Controlling terrain objectives | Rules Deep Dive: Terrain & Objectives

Control is checked at the end of each phase and turn by summing OC within the area - remember battle-shock's '-' contributes nothing. Rules that care whether a *unit* is "controlling" an objective need that unit to have a model with OC 1+ in range while its owner controls it: an OC0 unit can never satisfy such rules even standing next to friends who do. The Chapter Approved missions also label objectives as Home, Expansion (no-man's-land, offset toward one player) and Central, with the biggest mission rewards usually on Central - plan your commitment accordingly. The 40mm-marker rule in the appendix is strictly a fallback; terrain objectives are the intended way to play.

## @14.03 | Secured objectives matter more now | Rules Deep Dive: Terrain & Objectives

Securing existed piecemeal in 10th Edition rules text; now it's a core term. It matters more because *holding* objectives is more dangerous in 11th (even with Hidden): once secured, the objective stays yours even if the garrison is blasted to smithereens, until the enemy out-controls you at the end of a phase. Abilities that secure are worth building around.

## @19.01 | Leader + Support, locked at list-building | Rules Deep Dive: Special Unit Types

Two parallel attachment abilities: **Leader** and **Support**. Each unit can take one of each, which is how the old ad-hoc "two characters may join" rules are centralised. Support characters *must* attach - no more cheap solo characters squatting on objectives. Attachment happens in Muster Armies (army construction), not pre-game, so your doomstack is a permanent commitment. And it really is permanent: losing every **bodyguard** model, or the character to [PRECISION], no longer "destroys" any unit for rules purposes - the survivor is still the same **attached** unit. Mission-wise that means a Leader+Support+Bodyguard brick gives up one kill, not three; surviving characters still count as "leading a unit" for their own abilities; and revive effects can rebuild a wiped bodyguard around a lone survivor.

## @19.03 | Keyword targeting needs a living model | Rules Deep Dive: Special Unit Types

The attached unit has the union of all its datasheets' keywords, but each model keeps only its own. The app rules answer the classic question: an effect requiring a keyword can't affect or target the attached unit once every model with that keyword is destroyed - buff INTERCESSORS all you like, but at least one Intercessor must be alive. [ANTI] dodges the timing weirdness because it's evaluated when targets are selected, and models destroyed by attacks aren't removed until the attacking unit finishes all its attacks.

## @19.04 | Whose ability is it anyway? | Rules Deep Dive: Special Unit Types

While any model from the datasheet providing an ability survives, the whole attached unit benefits - so [PRECISION]-sniping the Leader still switches off their buffs. Bearer-only wargear abilities remain tied to the specific model. One open question flagged by the reviewers: whether datasheet-scoped core abilities like Feel No Pain or Infiltrators propagate unit-wide when only one datasheet has them - the attached-unit rules suggest yes, the ability wording suggests no. Expect an FAQ; until then agree a reading before the game.

## @17.01 | Big models walk out of traps | Rules Deep Dive: Special Unit Types

Monsters and Vehicles still can't move through *each other*, but when making a normal or advance move they can now pass through non-MONSTER/VEHICLE enemy models. Chaff rings no longer imprison a Carnifex - it simply strolls out (ending, as ever, outside engagement range, which at 2" per side is the real constraint).

## @17.03 | Shooting into a tied-up monster | Rules Deep Dive: Special Unit Types

You can always shoot at an engaged MONSTER/VEHICLE at -1 to hit; units actually engaged with it skip the penalty by using [CLOSE-QUARTERS] weapons. ([BLAST] weapons still cannot target an engaged unit at all.)

## @s23 | Aircraft make strafing runs now | Rules Deep Dive: Special Unit Types

Aircraft have no Move characteristic: they exist as **ingress moves** only. Each of your aircraft on the battlefield is returned to **strategic reserves** at the end of your opponent's turn, arriving again next turn - genuine strafing runs with a one-turn window for the enemy to shoot back. They must start in reserves (counting against your reserves points) so absent special abilities they act from battle round two. They can never charge; only **FLY** units can charge or melee them; enemies without FLY move through them freely and largely ignore them for "nearest unit" style rules - though their (huge) engagement range still blocks ending moves, which can awkwardly shield nearby targets from charges. They also no longer ignore the Obscuring rule when shooting or being shot, which - combined with board-edge arrivals - leaves them needing to be cheap to earn a slot.

## @24.28 | Precision in the save-group era | Ruleshammer: Save Groups, Precision & FNP

Precision now works through allocation groups: at the start of the Allocation Order step, if *any* attacking model with a [PRECISION] weapon can see a CHARACTER in the target unit (they don't all need line of sight - a change from 10th), the attacker picks that character's group as the current allocation group until the precision attacks resolve or the group dies. It selects a *single* character group - once that character is down, allocation reverts to normal; there is no clause to move on to a second character. Attacks that *gain* precision mid-resolution (e.g. on critical hits) are an open FAQ question - the pragmatic table reading is to resolve them as their own sub-group, similar to how [DEVASTATING WOUNDS] pools.

## @24.12 | Feel No Pain, per point of damage | Ruleshammer: Save Groups, Precision & FNP

Feel No Pain rolls happen per *wound that would be lost*, as each failed save's damage is allocated - a Damage 3 attack means three separate D6s. Save groups make the sequencing clean at last: allocate within the group, roll the model's FNPs as needed, and if it survives, keep allocating to it as normal. For variable damage (D6+2 etc.), roll the damage when the failed save is allocated so you know how many FNP dice to pick up.
