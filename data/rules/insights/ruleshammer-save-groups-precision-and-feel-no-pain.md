# Ruleshammer: Save Groups, Precision, and Feel No Pain
Series: Ruleshammer
Slug: ruleshammer-save-groups-precision-and-feel-no-pain
Order: 33
Source-Doc: Ruleshammer 11th Edition - Save Groups, Precision, and Feel No Pain.docx

*Welcome back to Ruleshammer! In this series we take a detailed look at the rules of key games, but Warhammer 40k in particular. This week we're looking at save groups, precision attacks, and feel no pain rolls!*

## Saving Groups 05.03

Saves in Warhammer 40k 11th edition are resolved in groups based on certain characteristics and keywords of the target unit. For most units there will be one group, but things get more complex if the unit has any variations in their Wound, Save, and Invulnerable Save characteristics or if the unit has any attached characters.

Create Groups: Divide all models in the target unit into the following groups, as many times as required:

  - One group for each CHARACTER model.
  - One group for all other models with the same W, Sv and InSv characteristics

![](ruleshammer-save-groups-precision-and-feel-no-pain-01.png)

Once you’ve identified your groups you need to allocate what order you’re going to resolve them in before you start making any saves. It’s not an entirely free choice though, some groups must be resolved before or after others based on a few key triggers.

Allocation Order: Declare the order in which those groups will have attacks allocated to them, applying all of the following:

  - If a non-CHARACTER group contains a model that has lost one or more wounds, that group must be first in the allocation order.
  - No CHARACTER group can be earlier in the allocation order than a non-CHARACTER group.
  - CHARACTER groups containing a model that has lost one or more wounds must be earlier in the allocation order than CHARACTER groups containing no wounded models.

![](ruleshammer-save-groups-precision-and-feel-no-pain-02.png)

One thing to note here is that wounded character groups don’t go ahead of non-character groups but you’re not forced to allocate to them first despite being wounded.

Generally this is all pretty easy to understand. Fast rolling saves has been something players “got on with” for several editions but without any codified structure other than the defacto understanding that fast rolling shouldn’t lead to a different outcome than slow rolling. 11th Edition is adding structure to saves as a fundamental concept so that it can then leverage that concept in other rules and abilities.

## Precision Attacks 24.28

No rule has leveraged the save groups system more than 11th edition’s version of Precision. This rule is a bit awkwardly worded, and I think many might actually manage to find a read of this that is more complex than is actually intended. It’s fully compatible with the new fast rolling of saves and shouldn’t actually lead to any new groupings, first let's look at the text of the ability one part at a time as it’s got a few moving parts.

While resolving attacks made with one or more \[PRECISION\] weapons,

So to start us off this ability applies any time **precision** weapons are used and because of how attack rolls are made in 11th you’ll never have a group of attacks to save against where only some of them have **precision** and some don’t. The "**identical attacks**” rule requires all attacks being resolved in a pool of attack dice have the same BS/WS, A, D, AP, **and** be affected by the same rules and abilities.

...at the start of the Allocation Order step (05.03), if the target unit contains one or more CHARACTER models visible to one or more of the attacking models, the active player can select one allocation group that contains one of those visible CHARACTER models.

This section is a bit clunky in my opinion and I can see people getting confused looking for a more complicated resolution to what is meant to be quite straight forward. If any of the models making those **precision** attacks can see a character model in the target unit then you can select the **allocation group** that character is in. They don’t all need to all be able to see the character, this is a pretty big change to how precision worked in 10th edition.

If they do, until those attacks are resolved, or until that CHARACTER group is destroyed (whichever happens first), that CHARACTER group is the current allocation group.

Finally we get to what all this actually does, it forces that chosen character group to become the “**current allocation group**”, which is a term the rules use for the group being resolved now. It doesn’t stay the current group after these attacks have been resolved though. Let's look at a diagrammed example of this in action.

![](ruleshammer-save-groups-precision-and-feel-no-pain-03.png)

## Attacks that gain Precision via a trigger

Some attacks can gain precision during the resolution of their attacks, such as if the attack gets a Critical Hit or Critical Wound. How to handle attacks that do this is potentially something we need an FAQ on, I have two distinct views on it as it stands now.

![](ruleshammer-save-groups-precision-and-feel-no-pain-04.png)

1. They could just become a sub pool of attacks you resolve as a group as if it was a group of attacks you'd made the normal way. So if you rolled 10 attacks where Critical Hits gained precision, and you rolled four critical hits, and 2 normal hits then you'd resolve this as if you had done them as two separate groups presumably with the active player chosing the order of the groups.
1. Potentially there's a pretty pedantic read that suggests that such attacks can't be fast rolled, to group attacks they all need to be "identical attacks" and such attacks must be affected by the same rules and abilities. The attacking player can't know which of their attacks will be affected by precision so they'd need to slow roll every single one. Not ideal.
I've seen some suggestions, especially for units that have several sources of attacks like this, that they should pool at the end like Devestation Wounds already do in 11th edition. This seems quite plausible.

## Precision into units with more than one Character

My read of the rule as it stands is that precision attacks only allow you to select a single character group to become the "current allocation group", once that character is destroyed normal allocation would resume. There's no clause to select a second character group if you have some precision attacks left to resolve.

## Feel No Pain 24.12

One question I’ve seen repeatedly so far is how this all interacts with the **Feel No Pain** ability, a rule which was probably one of the most difficult ones to resolve correctly when fast rolling saves in previous editions without adding in some level of advantaged information, especially with regard to re-rolls where fast rolling in previous editions caused you to do so with knowledge of what technically should have been future saves.

This ability always takes the form Feel No Pain X+. Each time a model with this ability would lose a wound, roll one D6: on an X+, that wound is not lost.

In 11th edition, the sequence is actually far far clearer. Saves in the new groups are resolved lowest to highest, as each one is allocated a model and if that model has a Feel No Pain you roll as needed for it at that step before moving on to the next wound roll you’re allocating. If the model survives the attack because the Feel No Pain rolls prevented enough damage, then you can continue allocating to that group/model as normal. Essentially the information advantage is sort of baked as intended now, though only for each set of attacks you're resolving. **Remember** that **Feel No Pain** rolls are PER DAMAGE, so if an attack has a Damage characteristic of 3 you need to roll a d6 for each of the 3 wounds it would otherwise inflict.

## What about attacks with dX damage?

Rules as written attacks with damage such as d6+2 should roll for damage when a failed save it allocated to a model, this way you know what number of wounds would be lost to determine how many Feel No Pain rolls to make.
