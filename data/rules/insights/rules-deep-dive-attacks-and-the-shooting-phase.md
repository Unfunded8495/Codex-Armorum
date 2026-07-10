# Rules Deep Dive: Attacks and the Shooting Phase
Series: Rules Deep Dive
Slug: rules-deep-dive-attacks-and-the-shooting-phase
Order: 13
Source-Doc: 11th Edition Rules Deep Dive - Attacks and the Shooting Phase.docx

This article is our deep dive on the Shooting Phase in 11th Edition, focusing on what’s changed in the new edition, and also covering changes to the process of making attacks that are relevant to the Fight Phase as well.

This piece is aimed primarily at existing players, and we’re going to focus on what’s changed rather than digging into the full mechanics of the phase. If you’re a brand new player looking to dive into 11th Edition, we recommend you go and take a look at our main review, as that provides a full outline of how Warhammer 40,000 works on the tabletop!

As a note - for our review, we have been provided with access to the extended digital rules that will be made generally available in the Warhammer 40,000 app. This means that in a few places, we may talk about a rule or specific nuance that hasn’t been covered in previews or things you’ve seen elsewhere. We’ll try to flag the important ones!

*Huge thanks to Games Workshop for providing us with review copies of all the material covered today. Please note that any digital material we refer to is subject to change until it is made available on Warhammer Community or the Warhammer 40k App.*

## Other Articles

If this isn’t the part of the rules you were looking for, or you’re wondering what to look at next, check out the links to all our deep dive articles below:

- [11th Edition 40k Rules Deep Dive: Core Concepts](#rules-deep-dive-core-concepts)
- [11th Edition 40k Rules Deep Dive: Command Phase](#rules-deep-dive-command-phase)
- [11th Edition 40k Rules Deep Dive: Moving and the Movement Phase](#rules-deep-dive-moving-and-the-movement-phase)
- [11th Edition 40k Rules Deep Dive: Attacks and the Shooting Phase](#rules-deep-dive-attacks-and-the-shooting-phase)
- [11th Edition 40k Rules Deep Dive: The Charge and Fight Phases](#rules-deep-dive-the-charge-and-fight-phases)
- [11th Edition 40k Rules Deep Dive: Terrain and Objectives](#rules-deep-dive-terrain-and-objectives)
- [11th Edition 40k Rules Deep Dive: Special Unit Types](#rules-deep-dive-special-unit-types)
- [11th Edition 40k Rules Deep Dive: Core Stratagems and Abilities](#rules-deep-dive-core-stratagems-and-abilities)

## Making Attacks

![](rules-deep-dive-attacks-and-the-shooting-phase-01.jpg)

Black Templars Assault Intercessors with Jump Packs. Credit: SRM

One of the biggest enduring issues for the last three editions has been that the sequence for processing attacks didn’t *fully* work in batches. “Fast Dice” was provided as a recommended option in all three cases, and in 10th Edition some extra changes *mostly* made it always work, but you still sometimes had to slow down and roll attacks one at a time.

11th Edition fully overhauls this with a comprehensive new set of rules for allocating attacks that makes batch execution the default, and it’s one of the biggest improvements in the rules for our money.

## Attack Sequence in 11th Edition

Making attacks in 11th Edition works as follows:

1. You select your unit’s targets. For ranged attacks, this needs to be a visible target in range of your unit, and you can split your unit’s weapons (for ranged attacks) or attacks (for melee) between multiple target units as long as they’re all eligible.
1. You select one of the units that was targeted, and then group all attacks allocated to that unit which are identical (with the same BS/WS, S, AP and D, plus the same special rules) to execute as a group.
1. Make hit rolls for that group of attacks. These work the same as in 10th - you have to beat your BS/WS score on a d6 to succeed.
1. Make wound rolls for that group of attacks. Again, same as in 10th - compare the S to the T of the enemy unit, and roll against a target number determined by that.
So far, all the same, and at the end of this you (hopefully) have a pool of successful Wounds. Now the new allocation rules kick in.

1. The enemy player separates their units into groups of models with identical defensive profiles, i.e. the same Save, Invulnerable Save and Wounds. Each Character goes in a separate group.
1. The enemy puts those groups in an **allocation** **order**. Character groups have to go after non-Character groups, and any group containing a Wounded model has to go ahead of groups without.
1. The enemy now rolls a saving throw for each successful Wound Roll, and then puts those dice in order from lowest roll to highest.
1. These saving throws are now resolved against the groups in the allocation order, starting with the lowest dice rolls (i.e. the first dice that are executed are any 1s rolled against the first allocation group). If a saving throw is below both the model’s Save (modified by AP) and Invulnerable Save characteristic, the attack inflicts damage on that model. If a model runs out of Wounds, they are destroyed.
1. You work through dice in order till you either run out of successful wounds, or run out of models to kill.
If there are still models alive in the unit, and you allocated other weapons to them, you then resolve those. After that, if other units were targeted, you move onto those, and repeat the above process.

![](rules-deep-dive-attacks-and-the-shooting-phase-02.jpg)

Credit: Keewa

There’s plenty to unpack here, but these are the big impacts:

- If the target unit has uniform defensive profiles, this doesn’t really change anything - it just makes everything faster.
- Units with mixed defensive profiles now have to fully plan their defensive ordering up front. It’s much harder to judiciously drop attacks on the perfect model one at a time.
- You now often want to put models with *worse* defensive profiles first, so that they absorb any 1s and 2s, and then hopefully by the time you get to the better defences, the enemy has run out of attacks.
- Leaders with 4+ Invulnerable saves are now meaningfully less likely to get killed by attacks spilling over from their unit, because if they have a bodyguard of any size, then lower rolls will hopefully be used up by the time attacks reach them.
- A small number of special Invulnerable Saves are extremely swingy with this rule. Models like Makari, Archons and users of some Enhancements that provide conditional 2+ Invulnerable Saves are almost unkillable via spillover damage, but will also die *instantly* if swung at when not in a unit.
There are a few technical points worth highlighting too:

- You do still need to slow down and process damage from attacks one at a time, either where the attack does random damage, or when hitting a model with a **Feel No Pain**.
- Invulnerable Saves are no longer optional - you can’t choose not to take them, they’re just part of your statline, and used to check if an attack succeeds.
- A targeted unit can switch up allocation order between different groups of attacks as long as they meet the criteria above, which can be possible as long as they’ve only lost whole models, and not left a multi-wound model lingering on the edge of death.
This generally ends up making mixed defensive profiles a bit less intrinsically valuable, particularly for units that had the option to tag in a single model with different stats, but can make some options that let you split defences down the middle more interesting. Bullgryn, for example, might find more value in splitting Slab and Brute shields 50:50, and then putting the higher Wound count and worse saves first in the allocation order to soak the bad dice against a particularly heavy onslaught.

## Mortal Wounds

![](rules-deep-dive-attacks-and-the-shooting-phase-03.jpg)

Credit: Robert "TheChirurgeon" Jones

Some attacks do Mortal Wounds as well as regular damage (mostly attacks with **Devastating Wounds**). These are now processed at the end of each group of identical attacks, rather than at the end of the whole unit’s attack sequence.

Some other effects can also cause Mortal Wounds. When allocating these, the rules for the order in which you do so largely match those for selecting allocation order, but outside of an attack sequence Mortal Wounds are applied one at a time, so each time a model is destroyed you do have the option to switch to a different type of model to take the next one.

## Cover

Shooting Attacks can be affected by Cover. We’ll get into how you gain cover in the Terrain Rules article, but for this one you need to know what it does, which is inflict a -1BS penalty to the firing unit. Because this is a BS modifier, it can stack with a -1 to Hit modifier as well, so any unit with access to a -1 to Hit effect that *isn’t* **Stealth** (which now just provides Cover) gets a lot better!

## The Shooting Phase

In the Shooting Phase, all your eligible units can shoot. By default, all your units that are on the battlefield and have not either shot or started an Action this turn are eligible, but some kinds of move (e.g. Fall-back) prevent them from doing so.

Each eligible unit can make attacks using one of four shooting modes, which are:

- Normal Shooting
- Assault Shooting
- Close-quarters Shooting
- Indirect Shooting
All types of shooting prevent you from being eligible to start an Action afterwards.

## Normal Shooting

This does exactly what it says on the tin - your unit makes attacks with their ranged weapons, following the sequence outlined above. They can only do this if they did not Advance this turn, and are not Engaged.

## Assault Shooting

![Dire Avengers. Credit: Rockfish](rules-deep-dive-attacks-and-the-shooting-phase-04.jpg)

Dire Avengers. Credit: Rockfish

You can select Assault Shooting if your unit Advanced and is not Engaged, and has one or more Assault Weapons. Your unit can shoot, but when doing so can only use Assault Weapons. This is pretty much identical to how Assault worked in the last few editions, but made into a Shooting mode to avoid weird rules lacunae around when shooting eligibility is checked.

## Close-Quarters Shooting

Close-Quarters Shooting combines the rules for Vehicles/Monsters shooting while in combat, and other units firing **Pistols** or **Close-Quarters** weapons. Your must be Engaged to select this mode, and if they’re not a Monster/Vehicle, must have at least one Close-Quarters/Pistol weapon.

When a Monster/Vehicle shoots in this mode, they can pick targets as normal, and can also pick any unit they’re engaged with as a target (unless firing a Blast weapon). However, when doing so they suffer -1 to Hit unless the weapon they are firing is **Close-Quarters**. Notably, because this is applying -1 to Hit, if they’re firing at an enemy unit in Cover they’ll be at -2 to Hit - and on top of this, the bonus for **Heavy** weapons no longer applies to units that are Engaged. This means that shooting out of combat can be a *lot* less effective than you’re used to in 10th Edition.

Other types of unit can also use this shooting mode, but when doing so they can only fire Close-Quarters weapons, and only at foes they are Engaged with. They don’t suffer any penalties for doing so.

## Indirect Shooting

![](rules-deep-dive-attacks-and-the-shooting-phase-05.jpg)

Death Korps of Krieg Artillery Team. Credit: SRM

Units that have one or more weapons with the **Indirect Fire** special rule can select this mode as long as they are unengaged and did not Advance.

When they do so, they can shoot their non-Indirect Fire weapons as normal, and their Indirect ones gain the ability to target foes that are not visible to them. However, this comes with a number of drawbacks, which apply to all Indirect Fire attacks made:

- The foe gains Cover against the attack.
- You cannot re-roll the hit roll.
- An unmodified hit roll of anything other than a 6 always fails unless your unit Remained Stationary, and at least one friendly unit can see the target (essentially acting as a spotter). In that case, an unmodified hit roll of a 1-3 always fails instead.
These are extremely punishing, and make Indirect Fire less good than it has been in the last few editions. You have to do more work to get to hit on a 4+ than previously, and even if you do that, not being able to re-roll hits strips away the main option that’s previously been used to get around the penalties. The effect is especially notable on units that bring a mix of Indirect and regular shooting like Fortis Kill Teams - now to get the full benefit of the Indirect, you’d have to sacrifice the whole unit’s movement. Also of note is that if you choose this mode, the penalties apply to your Indirect Fire weapons even if they target a visible foe, so for the vanishingly small number of units that have multiple different ones, you generally don’t want to do this if one of them is going into a juicy visible target.

The only small upside for Indirect Fire weapons in this edition is that a lot of them sit in the AP-1/AP-2 space which *really* benefits from the change to Cover, so each hit you do land has more impact (and essentially anything with BS3+ sees that as pure upside as long as they have a spotter). That doesn’t stop this being a pretty drastic reduction in the overall power of this ability, however.

## Wrap Up

That’s it for the Shooting Phase. If you want to read more about the rules, go check out our other deep dives from the links up top, or if you’re interested in models, missions or our overall opinions on 11th Edition, head back to the site’s front page, and you’ll find it all there.
