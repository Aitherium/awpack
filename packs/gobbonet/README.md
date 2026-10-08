# gobbonet

GobboNet is a local-first chat client. This pack puts a full agent loop behind
its chat box, and gives the loop a memory that understands *who knows what*.

## The problem it solves

Long campaigns decay. After a few hundred messages the model loops and forgets,
per-character knowledge is managed by hand, and the working fix today is a
human curating notes between scenes.

This pack makes the harness do that curation, on `awm`'s scope algebra:

    campaign : character : arc     ==     tenant : user : project

Three properties of that store carry the whole design:

- **A write lands at exactly one scope.** A secret recorded as known by Vex is
  Vex's, not the table's.
- **Siblings never see each other.** Two characters are sibling scopes, so one
  character's knowledge structurally cannot enter a scene the other is
  carrying. That *is* theory-of-mind — enforced by the store, not by prompt
  discipline.
- **A read includes ancestors.** Recalling for a character surfaces their facts
  plus campaign-wide world state, nearest first.

Recall is triggered by PRESENCE: a character's notes enter the scene brief only
when that character is named in the recent turns.

## Character cards and lorebooks

The formats people already trade, both directions:

- **Importing a card is a scoping decision, not a copy.** `personality`,
  `writingStyle` and `greeting` become notes only that character knows;
  `startingLore` becomes world state everyone knows.
- **Exporting reads one character's scope plus the world's**, so a card you
  hand to a player cannot carry a different character's secrets.
- Fields that are not imported are **named** in the result rather than dropped
  silently. `avatar` is never carried: it is an image belonging to the card's
  author.

## Illustration

`campaign_illustrate` draws a character (by card name or persona id) or a scene
from campaign memory through **your own** Media Forge, once you have connected
it in the Studio tab and confirmed what will be sent. Without that consent it
answers "not connected" and nothing leaves the machine.

- **The picture only shows what the viewpoint knows.** The prompt is built from
  that character's notes plus world state — exactly what `campaign_recall`
  returns. `scene` picks among those facts; it is never drawn verbatim, so a
  scene about another character's secret is refused before any request is sent.
- **Curated ops only.** Requests go to Media Forge's AitherSafety-tiered
  `/op/{name}` twins, never the owner's `/api/*`. A refusal comes back in Media
  Forge's own words.
- **The character stays the same character.** The first illustration renders a
  portrait and stores it as the character's reference *on their card*
  (`campaign_export_card` carries it as `reference`; import restores it). Later
  calls compose from that reference instead of re-rolling the face.
- Each illustration is recorded as a campaign note at the viewpoint's scope — a
  picture of a secret is itself a secret.

## Requires

`awm` (the `memory` extra). Without it the pack still runs — chat is unchanged,
the tools report what to install, and the scene brief is empty rather than
wrong.
