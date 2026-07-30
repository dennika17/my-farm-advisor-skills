# Local Instructions

## Purpose

This folder owns the soil depth interpolation workflow for computing depth-weighted
SSURGO soil properties at standard depth slices (0-10, 10-20, ..., 90-100 cm).

## Safe edit scope

Edits should stay in this folder and its children unless the user explicitly asks
for a broader skill change. Do not change parent `SKILL.md`, sibling soil workflows,
or root policy from a subskill task unless explicitly requested.

## Read nearby docs first

Read `GUIDE.md` first, then `examples/README.md` for examples.
If routing context is needed, read `../INDEX.md` and `../../SKILL.md`.

## Local validation

Run `./scripts/validate.sh` from the repository root after structural changes.
For functional testing, run the script against a known field and inspect the output
CSV files.

## Local-delta-only reminder

This nested AGENTS.md only records instructions that differ from the parent or root
files. Do not duplicate root-wide asset, vendor, or validation policy here except
this pointer to `../../../AGENTS.md`.
