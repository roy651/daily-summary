# Milestone reviews

Each milestone is reviewed by an external agent before the next one opens.

## Process

1. **Prepare** `REVIEW-<date>.md` (template below): list commits since the last review and a short
   scope note for the reviewer.
   ```
   git log <last-review-tag>..HEAD --oneline      # first review: git log --oneline
   ```
2. **External review** — hand the diff range + this note to the external reviewer.
3. **Response + fix cycle** — capture findings in the same file, address them, note resolutions.
4. **Tag** the reviewed commit `review-<date>` so the next range is unambiguous.

## Template

```markdown
# Review — <date>

## Scope
<what this milestone delivered; what to focus the review on>

## Commits since last review (<last-review-tag>..HEAD)
<git log --oneline output>

## Findings
- [ ] <finding> — <severity> — <resolution / commit>

## Sign-off
<reviewer> / <date>
```
