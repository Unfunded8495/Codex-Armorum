# Hammer of Math: The Benefit of Cover
Series: Hammer of Math
Slug: hammer-of-math-the-benefit-of-cover
Order: 50
Source-Doc: Hammer of Math - The Benefit of Cover in 11th Edition.docx

*In Hammer of Math, we look at various statistical concepts in Warhammer 40k, looking at how to evaluate different options mathematically and understanding how those probabilities and statistics affect your games. In this article we're looking at how the changes to cover affect weapons and damage output.*

Welcome back to Hammer of Math! It's been a while, hasn't it? We stopped posting for a while in part because I didn't have time for these and Primaris Kevin had stopped playing 40k and in part because we felt like we'd covered all of the key topics 10th edition had to offer. But now we've got an entirely new edition with entirely new math to talk about, and we should start with the biggest, gnarliest topic: Cover.

In tenth edition, the benefit of cover was +1 to your save, with some exceptions for models with 3+ and 2+ saves. In 11th edition, the benefit of cover has changed to being -1 BS for the attacking model, making your attacks less accurate. This has interesting knock-on effects for almost every weapon and unit in the game.

## The Value of Cover Is Variable

So let's start with the mathematical realities of the situation: In many situations, -1 BS for the attacking unit and +1 to saves will ***feel*** about the same. Take for example a unit of five Intercessors dumping 20 shots into a unit of ten Guardsmen.

In tenth edition, the Intercessors will hit with two-thirds (67%) of their attacks, hitting on 3+. They'll wound the same percentage (67%), as they wound on 3+, and the Guardsmen in cover will be +1 to their saves but suffer -1 AP from the bolt rifles, so they're saving on a 5+, or one third (33%) of the time. If we want to predict how many dead Guardsmen this gives us, the math is:

Shots \* (chance to hit) \* (chance to wound) \* (chance of an unsaved wound)

Now one thing to note here is that that thing up there is a product - it's four values multiplied by each other. Multiplication is commutative, so you can change the order of those values without changing the answer. In this case it'll be:

20 \* (2/3) \* (2/3) \* (2/3) = 20 \* (8/27) = 5.93

So we're looking an an average of around six dead Guardsmen. Now let's adjust the numbers for 11th edition. Now we're hitting on 4+ (50%), the Guardsmen's save will be modified to a 6+ (17%). Let's look at the math:

20 \* (1/2) \* (2/3) \* (5/6) = 20 \* (10/36) = 5.56

You are not going to feel that difference most of the time. Yes, 5.9 is higher than 5.6 but when those shots resolve, you're likely looking at 5-7 dead Guardsmen in either scenario.

In this case, I picked Guardsmen because it matters that they have a 5+ save. If I had picked Kasrkin or a unit with a 4+ save, the math would have instead been:

**10th:** 20 \* (2/3) \* (2/3) \* (1/2) = 20 \* (4/18) = 4.4

**11th:** 20 \* (1/2) \* (2/3) \* (2/3) = 20 \* (4/18) = 4.4

Making the result identical. Similarly, if we'd started with a 3+ save against AP-1 shooting, we'd have seen a marked improvement, as previously we'd expect to inflict 3 wounds against our imaginary Adepta Sororitas targets and now we can expect to see 3.3 pushed through. And this all assumes we're starting with BS 3+; if we start with BS 4+, our effectiveness drops more substantially.

That's because the value of +1 or -1 tends to be dependent on the value you start with and how big a percentage change that represents. Going from a 3+ to hit to a 2+ (an increase in accuracy of 25%) is not as big a deal as going from a 5+ to a 4+, where you get a 50% increase in accuracy. This ends up playing a major role in who benefits the most from 11th edition cover rules. This is also a handy time to go back to a chart we posted from the very first Hammer of Math:

| **Roll** | **Initial Probability** | **-1 Modifier Probability** | **Delta** | **+1 Modifier Probability** | **Delta** |
|---|---|---|---|---|---|
| 2+ | 83% | 67% | -20% | 83% | +0% |
| 3+ | 67% | 50% | -25% | 83% | +25% |
| 4+ | 50% | 33% | -33% | 67% | +33% |
| 5+ | 33% | 17% | -50% | 50% | +50% |
| 6+ | 17% | 0% | -100% | 33% | +100% |

The value of re-rolls is a bit different in that it's multiplicative and so their value does not vary based on the starting value.

## What This Means: AP -1 Weapons Really Matter Now

![](hammer-of-math-the-benefit-of-cover-01.jpg)

So to recap here: -1 to your Ballistic Skill is more impactful the worse your starting BS was, and improving saves is more impactful the worse your starting save was. Weapons which hit on a 3+ with AP-1, such as heavy bolters and autocannons in Marine armies, will see the biggest impacts here.

Heavy Bolters get an 11% bump when you factor in the impact of \[SUSTAINED HITS 1\] here, though again your value will depend on your starting Ballistic Skill. That said, if you're looking at Guardsmen, using Take Aim! ahead of time will give you similar results. Getting any AP at all is a bigger improvement than being more likely to hit for these weapons.

## The Other Major Factors

There are two other key factors here to consider, which can make doing the math behind cover in 11th edition tricky:

- **Hit Rolls have a floor.** That is, a roll of a 6 to hit always hits, regardless of modifiers, but a roll of a 6 to save does not always save - it's often possible to have an impossible save roll. This means AP modifiers can often be more impactful than hit modifiers.
- **Invulnerable saves.** The other major factor is invulnerable saves, which aren't affected by cover and cap the value of AP to begin with. Chaos Daemons in particular *only* have invulnerable saves and so the new cover rules are a flat upgrade for the army as an entire faction.

![](hammer-of-math-the-benefit-of-cover-02.jpg)

To get an idea of how these factors change things let's look at the main gun choices for the Chaos Space Marines Defiler: The Hades Lascannon and the Heavy Reaper Autocannon. The Hades has 2 shots at BS 3+, S13, AP-3 with D6+1 damage, while the Heavy Reaper is four shots at S9, AP-1, 3 damage with SUSTAINED HITS 1 and DEVASTATING WOUNDS.

![](hammer-of-math-the-benefit-of-cover-03.jpg)

Here the Hades Lascannon shooting into Terminator targets (or any target with a 2+/4+ save and 3 wounds), sees a noticeable drop in value in 11th edition thanks to the fact that the AP situation just didn't matter. Meanwhile the Autocannon just gets a substantial lift, becoming a more effective option given the extra shots - and that's *before* you factor in Devastating Wounds or the fact that the Lascannon will occasionally do 2 damage and not kill a Terminator.

In this last example, the Lascannon comes out on top at BS 3+ but quickly drops off as the number of extra shots from the Reaper helps it catch up (and again, this does not include devastating wounds). And even then, the difference is much, much smaller than it used to be - the 10th edition double lascannon delivered double or more of the value of the autocannon even with half the shots, albeit with the occasional risk of rolling low on damage.

## Final Thoughts

Ultimately, the big winners here are models with good invulnerable saves and weapons with a high volume of AP-1 shooting, as those are the units which see the largest net benefit from the new cover rules. Meanwhile low-volume, high-"value" shooting weapons like multi-meltas and lascannons see a comparative drop, as they both become more volatile and less effective - and that will be even more true for units with worse starting Ballistic Skill characteristics. Being able to do D6+1 damage will still have value - the twin lascannon in our example still out-paced the Heavy Reaper Autocannon for shooting units with a starting Ballistic Skill of 4+ or better - but you're going to have to weigh that against the higher chance of just whiffing your shots.

There are a number of other more specific examples we can look at in the coming weeks, and you can expect us to do that, diving into how these changes affect specific units and their weapon options.
