# Import Provenance Template

Every imported skill or source snapshot in this repository must ship with a provenance record that is committed alongside the import.

## Required record for every import

Use the template below for each import. Keep every field present. If a field does not apply, write `N/A` and explain why.

```md
## <import-name>
- source_repo: <git URL or N/A when local-only>
- source_local_path: <absolute local path or N/A when remote-only>
- source_ref: <branch or tag used for the import>
- source_commit: <resolved 40-character SHA or N/A when there is no clean commit snapshot>
- source_status: <clean remote ref | clean worktree | modified worktree | untracked worktree | detached HEAD | N/A>
- source_path: <path within the source repo/worktree>
- destination_path: <path within this repository>
- import_date: <YYYY-MM-DD>
- exclusions: <files, directories, assets, or behaviors intentionally not imported>
- local_modifications: <changes made after copy/import relative to the recorded source>
- update_procedure: <exact steps to refresh from upstream>
```

## Source-ref verification policy

1. Resolve every remote branch or tag to a commit SHA before copying files. Never record only a branch name.
2. For authenticated Omni/Wrighter imports, run this precheck before import or refresh:

   ```bash
   git ls-remote https://github.com/borealBytes/omni.git refs/heads/feature/wrighter-delivery
   ```

   Record the returned SHA as `source_commit` and keep `source_ref: feature/wrighter-delivery`.
3. For public remotes, record the exact ref plus the resolved SHA from `git ls-remote <repo> refs/heads/<branch>` or `refs/tags/<tag>`.
4. For local worktrees, capture all of the following before import:

   ```bash
   git branch --show-current
   git rev-parse HEAD
   git status --short
   ```

   Record the branch/tag in `source_ref`, the HEAD SHA in `source_commit`, and the worktree state in `source_status`.
5. If the imported content comes from uncommitted local worktree files, explicitly say so in `source_status` (for example `untracked worktree: scientific-skills/breeding-trial-management/`).
6. Update or refresh work must repeat the same verification step and replace the recorded SHA/status before files are copied.

## Update checklist

1. Re-run the source-ref verification step.
2. Compare current upstream/local content against the last recorded `source_commit` or `source_status`.
3. Re-copy only the intended `source_path` into `destination_path`.
4. Re-apply any `local_modifications` intentionally kept in this repo.
5. Update the provenance record, manifest entry, and related QA evidence in the same commit.

## my-farm-breeding-trial-management
- source_repo: https://github.com/borealBytes/my-farm-advisor.git
- source_local_path: /media/clay/Data/dev/scientific-agent-skills-worktrees/scientific-agent-skills-breeding-trial-management
- source_ref: feat/breeding-trial-management
- source_commit: f479f5d2d494d12c8b60fbdc338bf1219dd5a0d1
- source_status: untracked worktree: scientific-skills/breeding-trial-management/
- source_path: scientific-skills/breeding-trial-management/
- destination_path: my-farm-breeding-trial-management/
- import_date: 2026-04-28
- remote_baseline_ref: main
- remote_baseline_commit: 4a82ab779e8374035ca5e15f1cb1c0571395dc3d
- remote_baseline_path: skills/my-farm-breeding-trial-management/
- exclusions: `.git/`; any unrelated scientific skills outside `scientific-skills/breeding-trial-management/`; remote flat-layout paths that would overwrite the grouped local example taxonomy
- local_modifications: Copied the local untracked skill tree as the structural base; added root `README.md` from the remote skill with grouped-path adjustments; backfilled remote-only `scripts/breeding_cli.py` and `examples/field-trial-placement/`; merged remote unified-CLI/tool-selection documentation into local `SKILL.md` while preserving local grouped examples and local `references/bms-api.md` + `references/breedbase-api.md`.
- update_procedure: Re-run `git branch --show-current`, `git rev-parse HEAD`, and `git status --short` in `/media/clay/Data/dev/scientific-agent-skills-worktrees/scientific-agent-skills-breeding-trial-management`; copy only `scientific-skills/breeding-trial-management/` into `my-farm-breeding-trial-management/`; resolve `https://github.com/borealBytes/my-farm-advisor.git` `main` to a commit SHA; then re-apply the remote completeness backfill for `README.md`, `scripts/breeding_cli.py`, and `examples/field-trial-placement/` without replacing the grouped local taxonomy or adjusted reference files.

## my-farm-advisor
- source_repo: https://github.com/borealBytes/my-farm-advisor.git
- source_local_path: N/A
- source_ref: main
- source_commit: 4a82ab779e8374035ca5e15f1cb1c0571395dc3d
- source_status: clean remote ref
- source_path: skills/my-farm-advisor/
- destination_path: my-farm-advisor/
- import_date: 2026-04-28
- exclusions: `.git/`; generated geoadmin runtime payloads such as `data-pipeline/src/shared/geoadmin/l0_countries/countries.geojson`, `data-pipeline/src/shared/geoadmin/l1_states/states_usa.geojson`, and runtime-parity outputs that are rebuilt under `data/my-farm-advisor/shared/geoadmin/{l0_countries,l1_states,l2_counties}/`; generated maturity report/table artifacts under `data-pipeline/src/shared/*/{reports,tables}/`; any repo-local CI or deployment files outside `skills/my-farm-advisor/`
- local_modifications: Imported `skills/my-farm-advisor/` into `my-farm-advisor/` and intentionally kept geoadmin source metadata JSON files while excluding generated geoadmin payloads. The committed metadata records the upstream `source_url`, `archive_name`, `output_geojson`, and `output_parquet` values used by `data-pipeline/src/scripts/ingest/download_geoadmin.py` to rebuild runtime outputs under `data/my-farm-advisor/shared/geoadmin/{l0_countries,l1_states,l2_counties}/`. Generated maturity report/table artifacts were also omitted while preserving `farm_dashboard.py`, `run_farm_pipeline.py`, and `run_maturity_by_fips.py`.
- update_procedure: Run `git ls-remote https://github.com/borealBytes/my-farm-advisor.git refs/heads/main`, confirm the SHA, clone or fetch the repo, copy only `skills/my-farm-advisor/` into `my-farm-advisor/`, preserve the geoadmin metadata JSON files, exclude generated geoadmin payloads and runtime copies that belong under `data/my-farm-advisor/shared/geoadmin/{l0_countries,l1_states,l2_counties}/`, exclude generated maturity report/table artifacts under `data-pipeline/src/shared/*/{reports,tables}/`, rerun `./scripts/validate.sh`, and refresh the QA evidence plus provenance fields in the same commit.

## my-farm-qtl-analysis
- source_repo: https://github.com/borealBytes/my-farm-advisor.git
- source_local_path: /media/clay/Data/dev/scientific-agent-skills-worktrees/scientific-agent-skills-qtl-analysis
- source_ref: feat/qtl-analysis
- source_commit: f479f5d2d494d12c8b60fbdc338bf1219dd5a0d1
- source_status: untracked worktree: scientific-skills/qtl-analysis/
- source_path: scientific-skills/qtl-analysis/
- destination_path: my-farm-qtl-analysis/
- import_date: 2026-04-28
- remote_baseline_ref: main
- remote_baseline_commit: 4a82ab779e8374035ca5e15f1cb1c0571395dc3d
- remote_baseline_path: skills/my-farm-qtl-analysis/
- exclusions: `.git/`; generated `examples/**/output/` artifacts; generated `scripts/output/` artifacts; no unrelated scientific skills outside `scientific-skills/qtl-analysis/`; no remote flattening of the local grouped example taxonomy
- local_modifications: Imported the local grouped example layout as the structural base, backfilled remote-only `README.md` and `scripts/qtl_cli.py`, merged richer remote SKILL sections without changing example-first behavior, normalized local-source path assumptions to `my-farm-qtl-analysis/`, preserved `scripts/verify_gpu_hpc.py` and `VISUALIZATION_SUMMARY.md`, and excluded generated outputs after asset audit.
- update_procedure: Re-run `git ls-remote https://github.com/borealBytes/my-farm-advisor.git refs/heads/main`, capture the resolved baseline SHA for `skills/my-farm-qtl-analysis`, re-run `git branch --show-current`, `git rev-parse HEAD`, and `git status --short` in `/media/clay/Data/dev/scientific-agent-skills-worktrees/scientific-agent-skills-qtl-analysis`, copy only `scientific-skills/qtl-analysis/` into `my-farm-qtl-analysis/`, re-apply the remote backfill files and grouped-path normalization, repeat the asset audit, and refresh this provenance record plus `IMPORT_MANIFEST.md` in the same commit.

## soil-depth-interpolation (my-farm-advisor subskill)
- source_repo: N/A
- source_local_path: N/A
- source_ref: N/A
- source_commit: N/A
- source_status: N/A
- source_path: N/A
- destination_path: my-farm-advisor/soil/soil-depth-interpolation/
- import_date: 2026-07-28
- exclusions: N/A
- local_modifications: Created as a new local subskill extending my-farm-advisor/soil/ssurgo-soil. Fetches full USDA SSURGO data (all components, all horizons) and computes depth-interpolated soil properties at 10 cm resolution. Produces ssurgo_full_regenerated.csv, ssurgo_full_with_components.csv, and ssurgo_full_depth_interpolated.csv per field.
- update_procedure: Edit files directly in my-farm-advisor/soil/soil-depth-interpolation/; run ./scripts/validate.sh before committing.
