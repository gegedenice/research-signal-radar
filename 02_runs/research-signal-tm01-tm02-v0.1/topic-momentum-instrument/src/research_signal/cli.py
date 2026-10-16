from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import load_config
from .ca01 import run_ca01
from .ca02 import run_ca02
from .ca03 import run_ca03
from .ca04 import run_ca04
from .acn01 import run_acn01
from .acn02 import run_acn02
from .acn03 import run_acn03
from .acn04 import run_acn04
from .errors import ResearchSignalError
from .openalex import OpenAlexClient
from .opencitations import OpenCitationsClient
from .tm01 import run_tm01
from .tm02 import run_tm02
from .tm03 import run_tm03
from .tm04 import run_tm04
from .tm05 import run_tm05
from .tm06 import run_tm06
from .tm07 import run_tm07
from .tm08 import run_tm08


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research-signal",
        description="Run the Research Signal detector pipeline.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    tm01 = sub.add_parser("tm01", help="Resolve ROR, archive lineage and write manifests")
    tm01.add_argument("--config", required=True, type=Path)

    tm02 = sub.add_parser("tm02", help="Collect monthly census and work observations")
    tm02.add_argument("--config", required=True, type=Path)
    tm02.add_argument("--scope", required=True, choices=["exact", "lineage", "curated_set"])
    tm02.add_argument(
        "--resume",
        action="store_true",
        help="Reuse a completed census and continue an interrupted work sweep.",
    )

    tm03 = sub.add_parser("tm03", help="Build dense monthly series and rolling windows")
    tm03.add_argument("--config", required=True, type=Path)
    tm03.add_argument("--scope", required=True, choices=["exact", "lineage", "curated_set"])
    tm03_mode = tm03.add_mutually_exclusive_group()
    tm03_mode.add_argument(
        "--resume",
        action="store_true",
        help="Return an already completed TM-03 result without overwriting artifacts.",
    )
    tm03_mode.add_argument(
        "--rebuild",
        action="store_true",
        help="Regenerate TM-03 series and quality artifacts, overwriting them.",
    )

    tm04 = sub.add_parser("tm04", help="Classify topic presence, direction and acceleration")
    tm04.add_argument("--config", required=True, type=Path)
    tm04.add_argument("--scope", required=True, choices=["exact", "lineage", "curated_set"])
    tm04_mode = tm04.add_mutually_exclusive_group()
    tm04_mode.add_argument(
        "--resume",
        action="store_true",
        help="Return an already completed TM-04 result without overwriting artifacts.",
    )
    tm04_mode.add_argument(
        "--rebuild",
        action="store_true",
        help="Regenerate TM-04 classifications and quality artifacts, overwriting them.",
    )

    tm05 = sub.add_parser("tm05", help="Apply confidence and parameter-sensitivity guards")
    tm05.add_argument("--config", required=True, type=Path)
    tm05.add_argument("--scope", required=True, choices=["exact", "lineage", "curated_set"])
    tm05_mode = tm05.add_mutually_exclusive_group()
    tm05_mode.add_argument(
        "--resume",
        action="store_true",
        help="Return an already completed TM-05 result without overwriting artifacts.",
    )
    tm05_mode.add_argument(
        "--rebuild",
        action="store_true",
        help="Regenerate TM-05 confidence and quality artifacts, overwriting them.",
    )

    tm06 = sub.add_parser("tm06", help="Emit ranked signals and evidence dossiers")
    tm06.add_argument("--config", required=True, type=Path)
    tm06.add_argument("--scope", required=True, choices=["exact", "lineage", "curated_set"])
    tm06_mode = tm06.add_mutually_exclusive_group()
    tm06_mode.add_argument(
        "--resume",
        action="store_true",
        help="Return an already completed TM-06 result without overwriting artifacts.",
    )
    tm06_mode.add_argument(
        "--rebuild",
        action="store_true",
        help="Regenerate only TM-06 derived artifacts with the current emitter.",
    )

    tm07 = sub.add_parser("tm07", help="Replay eligible signals at historical cutoffs")
    tm07.add_argument("--config", required=True, type=Path)
    tm07.add_argument("--scope", required=True, choices=["exact", "lineage", "curated_set"])
    tm07_mode = tm07.add_mutually_exclusive_group()
    tm07_mode.add_argument(
        "--resume",
        action="store_true",
        help="Return an already completed TM-07 replay from the same emitter.",
    )
    tm07_mode.add_argument(
        "--rebuild",
        action="store_true",
        help="Regenerate only TM-07 replay artifacts with the current emitter.",
    )

    tm08 = sub.add_parser("tm08", help="Evaluate replay outcomes and episodes")
    tm08.add_argument("--config", required=True, type=Path)
    tm08.add_argument("--scope", required=True, choices=["exact", "lineage", "curated_set"])
    tm08_mode = tm08.add_mutually_exclusive_group()
    tm08_mode.add_argument(
        "--resume",
        action="store_true",
        help="Return an already completed TM-08 evaluation from the same version.",
    )
    tm08_mode.add_argument(
        "--rebuild",
        action="store_true",
        help="Regenerate only TM-08 outcome artifacts with the current evaluator.",
    )

    ca01 = sub.add_parser(
        "ca01", help="Collect and normalize incoming OpenCitations events"
    )
    ca01.add_argument("--config", required=True, type=Path)
    ca01.add_argument(
        "--scope", required=True, choices=["exact", "lineage", "curated_set"]
    )
    ca01_mode = ca01.add_mutually_exclusive_group()
    ca01_mode.add_argument(
        "--resume",
        action="store_true",
        help="Reuse cached DOI responses and continue an interrupted collection.",
    )
    ca01_mode.add_argument(
        "--rebuild",
        action="store_true",
        help="Renormalize CA-01 only from cached OpenCitations responses.",
    )

    ca02 = sub.add_parser(
        "ca02", help="Build citation windows, cohorts and explicit abstentions"
    )
    ca02.add_argument("--config", required=True, type=Path)
    ca02.add_argument(
        "--scope", required=True, choices=["exact", "lineage", "curated_set"]
    )
    ca02_mode = ca02.add_mutually_exclusive_group()
    ca02_mode.add_argument(
        "--resume",
        action="store_true",
        help="Return an already completed CA-02 result from the same version.",
    )
    ca02_mode.add_argument(
        "--rebuild",
        action="store_true",
        help="Regenerate only CA-02 derived artifacts from CA-01.1 inputs.",
    )

    ca03 = sub.add_parser(
        "ca03", help="Select, rank and explain citation-acceleration signals"
    )
    ca03.add_argument(
        "--config", required=True, type=Path
    )
    ca03.add_argument(
        "--scope", required=True, choices=["exact", "lineage", "curated_set"]
    )
    ca03_mode = ca03.add_mutually_exclusive_group()
    ca03_mode.add_argument(
        "--resume", action="store_true",
        help="Return an already completed CA-03 result from the same emitter.",
    )
    ca03_mode.add_argument(
        "--rebuild", action="store_true",
        help="Regenerate only CA-03 signals and evidence from CA-02.",
    )

    ca04 = sub.add_parser(
        "ca04", help="Replay citation acceleration and evaluate 12-month outcomes"
    )
    ca04.add_argument("--config", required=True, type=Path)
    ca04.add_argument(
        "--scope", required=True, choices=["exact", "lineage", "curated_set"]
    )
    ca04_mode = ca04.add_mutually_exclusive_group()
    ca04_mode.add_argument(
        "--resume", action="store_true",
        help="Return an already completed CA-04 result from the same evaluator.",
    )
    ca04_mode.add_argument(
        "--rebuild", action="store_true",
        help="Regenerate only the offline CA-04 replay and outcomes.",
    )

    acn01 = sub.add_parser(
        "acn01", help="Normalize institutional collaboration and coaffiliation events"
    )
    acn01.add_argument("--config", required=True, type=Path)
    acn01.add_argument(
        "--scope", required=True, choices=["exact", "lineage", "curated_set"]
    )
    acn01_mode = acn01.add_mutually_exclusive_group()
    acn01_mode.add_argument(
        "--resume", action="store_true",
        help="Return an already completed ACN-01 result from the same normalizer.",
    )
    acn01_mode.add_argument(
        "--rebuild", action="store_true",
        help="Renormalize ACN-01 offline from existing WorkObservations.",
    )

    acn02 = sub.add_parser(
        "acn02", help="Build actor/edge histories, candidates and abstentions"
    )
    acn02.add_argument("--config", required=True, type=Path)
    acn02.add_argument(
        "--scope", required=True, choices=["exact", "lineage", "curated_set"]
    )
    acn02_mode = acn02.add_mutually_exclusive_group()
    acn02_mode.add_argument(
        "--resume", action="store_true",
        help="Return an already completed ACN-02 result from the same calculator.",
    )
    acn02_mode.add_argument(
        "--rebuild", action="store_true",
        help="Regenerate only ACN-02 histories and candidates from ACN-01.",
    )

    acn03 = sub.add_parser(
        "acn03", help="Rank and explain actor/collaboration novelty signals"
    )
    acn03.add_argument("--config", required=True, type=Path)
    acn03.add_argument(
        "--scope", required=True, choices=["exact", "lineage", "curated_set"]
    )
    acn03_mode = acn03.add_mutually_exclusive_group()
    acn03_mode.add_argument(
        "--resume", action="store_true",
        help="Return an already completed ACN-03 result from the same emitter.",
    )
    acn03_mode.add_argument(
        "--rebuild", action="store_true",
        help="Regenerate only ACN-03 signals, evidence and dossier.",
    )

    acn04 = sub.add_parser(
        "acn04", help="Replay actor/collaboration novelty and evaluate 12-month outcomes"
    )
    acn04.add_argument("--config", required=True, type=Path)
    acn04.add_argument(
        "--scope", required=True, choices=["exact", "lineage", "curated_set"]
    )
    acn04_mode = acn04.add_mutually_exclusive_group()
    acn04_mode.add_argument(
        "--resume", action="store_true",
        help="Return an already completed ACN-04 result from the same evaluator.",
    )
    acn04_mode.add_argument(
        "--rebuild", action="store_true",
        help="Regenerate only the offline ACN-04 replay and outcomes.",
    )

    run = sub.add_parser("run", help="Run TM-01 then TM-02 for one or more scopes")
    run.add_argument("--config", required=True, type=Path)
    run.add_argument(
        "--scope",
        action="append",
        choices=["exact", "lineage", "curated_set"],
        help="Repeat to run several scopes; defaults to all configured scopes.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        config = load_config(args.config)
        if args.command == "acn04":
            run_dir = config.output_root / config.run_id
            result = run_acn04(
                config, run_dir, args.scope, resume=args.resume, rebuild=args.rebuild
            )
            output = {
                "stage": "ACN-04",
                "scope": result.scope_mode,
                "scope_dir": str(result.scope_dir),
                "cutoff_count": result.cutoff_count,
                "eligible_cutoff_count": result.eligible_cutoff_count,
                "replayed_signal_count": result.replayed_signal_count,
                "observed_outcome_count": result.observed_outcome_count,
                "censored_outcome_count": result.censored_outcome_count,
                "continued_outcome_count": result.continued_outcome_count,
                "quality_report": str(result.quality_report_path),
            }
        elif args.command == "acn03":
            run_dir = config.output_root / config.run_id
            result = run_acn03(
                config, run_dir, args.scope, resume=args.resume, rebuild=args.rebuild
            )
            output = {
                "stage": "ACN-03",
                "scope": result.scope_mode,
                "scope_dir": str(result.scope_dir),
                "candidate_count": result.candidate_count,
                "signal_count": result.signal_count,
                "headline_candidate_count": result.headline_candidate_count,
                "review_required_count": result.review_required_count,
                "dossier_selected_count": result.dossier_selected_count,
                "evidence_mismatch_count": result.evidence_mismatch_count,
                "quality_report": str(result.quality_report_path),
            }
        elif args.command == "acn02":
            run_dir = config.output_root / config.run_id
            result = run_acn02(
                config, run_dir, args.scope, resume=args.resume, rebuild=args.rebuild
            )
            output = {
                "stage": "ACN-02",
                "scope": result.scope_mode,
                "scope_dir": str(result.scope_dir),
                "actor_history_count": result.actor_history_count,
                "edge_history_count": result.edge_history_count,
                "assessment_count": result.assessment_count,
                "candidate_count": result.candidate_count,
                "actor_candidate_count": result.actor_candidate_count,
                "collaboration_candidate_count": result.collaboration_candidate_count,
                "quality_report": str(result.quality_report_path),
            }
        elif args.command == "acn01":
            run_dir = config.output_root / config.run_id
            result = run_acn01(
                config, run_dir, args.scope, resume=args.resume, rebuild=args.rebuild
            )
            output = {
                "stage": "ACN-01",
                "scope": result.scope_mode,
                "scope_dir": str(result.scope_dir),
                "input_work_count": result.input_work_count,
                "usable_work_count": result.usable_work_count,
                "collaboration_event_count": result.collaboration_event_count,
                "coaffiliation_event_count": result.coaffiliation_event_count,
                "unique_external_institution_count": result.unique_external_institution_count,
                "quality_report": str(result.quality_report_path),
            }
        elif args.command == "ca04":
            run_dir = config.output_root / config.run_id
            result = run_ca04(
                config, run_dir, args.scope, resume=args.resume, rebuild=args.rebuild
            )
            output = {
                "stage": "CA-04",
                "scope": result.scope_mode,
                "scope_dir": str(result.scope_dir),
                "cutoff_count": result.cutoff_count,
                "replayed_signal_count": result.replayed_signal_count,
                "observed_outcome_count": result.observed_outcome_count,
                "censored_outcome_count": result.censored_outcome_count,
                "sustained_outcome_count": result.sustained_outcome_count,
                "quality_report": str(result.quality_report_path),
            }
        elif args.command == "ca03":
            run_dir = config.output_root / config.run_id
            result = run_ca03(
                config, run_dir, args.scope, resume=args.resume, rebuild=args.rebuild
            )
            output = {
                "stage": "CA-03",
                "scope": result.scope_mode,
                "scope_dir": str(result.scope_dir),
                "candidate_count": result.candidate_count,
                "signal_count": result.signal_count,
                "headline_candidate_count": result.headline_candidate_count,
                "review_required_count": result.review_required_count,
                "quality_report": str(result.quality_report_path),
            }
        elif args.command == "ca02":
            run_dir = config.output_root / config.run_id
            result = run_ca02(
                config,
                run_dir,
                args.scope,
                resume=args.resume,
                rebuild=args.rebuild,
            )
            output = {
                "stage": "CA-02",
                "scope": result.scope_mode,
                "scope_dir": str(result.scope_dir),
                "assessment_count": result.assessment_count,
                "eligible_count": result.eligible_count,
                "abstained_count": result.abstained_count,
                "cohort_count": result.cohort_count,
                "quality_report": str(result.quality_report_path),
            }
        elif args.command == "ca01":
            run_dir = config.output_root / config.run_id
            with OpenCitationsClient(config.opencitations) as client:
                result = run_ca01(
                    config,
                    client,
                    run_dir,
                    args.scope,
                    resume=args.resume,
                    rebuild=args.rebuild,
                )
            output = {
                "stage": "CA-01",
                "scope": result.scope_mode,
                "scope_dir": str(result.scope_dir),
                "input_work_count": result.input_work_count,
                "eligible_work_count": result.eligible_work_count,
                "collected_work_count": result.collected_work_count,
                "citation_event_count": result.citation_event_count,
                "quality_report": str(result.quality_report_path),
            }
        elif args.command == "tm03":
            run_dir = config.output_root / config.run_id
            result = run_tm03(
                config, run_dir, args.scope, resume=args.resume, rebuild=args.rebuild
            )
            output = {
                "stage": "TM-03",
                "scope": result.scope_mode,
                "scope_dir": str(result.scope_dir),
                "topic_count": result.topic_count,
                "month_count": result.month_count,
                "evaluation_count": result.evaluation_count,
            }
        elif args.command == "tm04":
            run_dir = config.output_root / config.run_id
            result = run_tm04(
                config, run_dir, args.scope, resume=args.resume, rebuild=args.rebuild
            )
            output = {
                "stage": "TM-04",
                "scope": result.scope_mode,
                "scope_dir": str(result.scope_dir),
                "classification_count": result.classification_count,
                "latest_topic_count": result.latest_topic_count,
                "candidate_count": result.candidate_count,
            }
        elif args.command == "tm05":
            run_dir = config.output_root / config.run_id
            result = run_tm05(
                config, run_dir, args.scope, resume=args.resume, rebuild=args.rebuild
            )
            output = {
                "stage": "TM-05",
                "scope": result.scope_mode,
                "scope_dir": str(result.scope_dir),
                "assessment_count": result.assessment_count,
                "latest_candidate_count": result.latest_candidate_count,
                "eligible_count": result.eligible_count,
            }
        elif args.command == "tm06":
            run_dir = config.output_root / config.run_id
            result = run_tm06(
                config,
                run_dir,
                args.scope,
                resume=args.resume,
                rebuild=args.rebuild,
            )
            output = {
                "stage": "TM-06",
                "scope": result.scope_mode,
                "scope_dir": str(result.scope_dir),
                "signal_count": result.signal_count,
                "representative_work_count": result.representative_work_count,
                "evidence_mismatch_count": result.evidence_mismatch_count,
                "headline_candidate_count": result.headline_candidate_count,
                "review_required_count": result.review_required_count,
            }
        elif args.command == "tm07":
            run_dir = config.output_root / config.run_id
            result = run_tm07(
                config,
                run_dir,
                args.scope,
                resume=args.resume,
                rebuild=args.rebuild,
            )
            output = {
                "stage": "TM-07",
                "scope": result.scope_mode,
                "scope_dir": str(result.scope_dir),
                "cutoff_count": result.cutoff_count,
                "replayed_signal_count": result.replayed_signal_count,
                "headline_candidate_count": result.headline_candidate_count,
                "review_required_count": result.review_required_count,
                "evidence_mismatch_count": result.evidence_mismatch_count,
            }
        elif args.command == "tm08":
            run_dir = config.output_root / config.run_id
            result = run_tm08(
                config,
                run_dir,
                args.scope,
                resume=args.resume,
                rebuild=args.rebuild,
            )
            output = {
                "stage": "TM-08",
                "scope": result.scope_mode,
                "scope_dir": str(result.scope_dir),
                "event_outcome_count": result.event_outcome_count,
                "observed_outcome_count": result.observed_outcome_count,
                "censored_outcome_count": result.censored_outcome_count,
                "episode_count": result.episode_count,
                "headline_episode_count": result.headline_episode_count,
                "review_sample_count": result.review_sample_count,
            }
        else:
            with OpenAlexClient(config.openalex) as client:
                if args.command == "tm01":
                    result = run_tm01(config, client)
                    output = {
                        "stage": "TM-01",
                        "run_dir": str(result.run_dir),
                        "root_institution_id": result.root_institution_id,
                        "manifests": {
                            mode: str(path) for mode, path in result.manifest_paths.items()
                        },
                    }
                elif args.command == "tm02":
                    run_dir = config.output_root / config.run_id
                    result = run_tm02(config, client, run_dir, args.scope, resume=args.resume)
                    output = {
                        "stage": "TM-02",
                        "scope": result.scope_mode,
                        "scope_dir": str(result.scope_dir),
                        "bucket_count": result.bucket_count,
                        "topic_row_count": result.topic_row_count,
                        "observation_count": result.observation_count,
                    }
                else:
                    tm01_result = run_tm01(config, client)
                    scopes = args.scope or list(config.universe.scope_modes)
                    tm02_results = [
                        run_tm02(config, client, tm01_result.run_dir, scope)
                        for scope in scopes
                    ]
                    output = {
                        "stage": "TM-01+TM-02",
                        "run_dir": str(tm01_result.run_dir),
                        "root_institution_id": tm01_result.root_institution_id,
                        "scopes": [
                            {
                                "scope": item.scope_mode,
                                "bucket_count": item.bucket_count,
                                "topic_row_count": item.topic_row_count,
                                "observation_count": item.observation_count,
                                "scope_dir": str(item.scope_dir),
                            }
                            for item in tm02_results
                        ],
                    }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except (ResearchSignalError, OSError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
