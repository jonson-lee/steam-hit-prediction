"""Descriptive EDA over the accepted package; never produce X/y or fit a model.

Run from the repository root with python -B -m scripts.reproduce_data_eda.
Every execution creates a fresh outputs/data_eda/<UTC>/ directory. Raw inputs,
the accepted package and current implementation are protected for this run.
Published reports and the sealed X/y package are never overwritten.
"""
import argparse
import csv
import json
import math
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MPLCONFIGDIR", tempfile.mkdtemp(prefix="steam-eda-mpl-"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import config
from src.steam_handoff import file_hash, read_table, strict_json_loads, verify_package
from src.project_paths import find_steam_csv

PACKAGE = ROOT / "data/processed/steam_handoff_v12"
SPLITS = ("train", "validation", "test")
SEQ = config.DATA_PARSE_POLICY["sequences"]["fields"]


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")


def protected_snapshot(raw_directory, input_names):
    """Rebuild both inventory and hashes; additions/removals also fail equality."""
    implementation = {
        ROOT / "config.py", Path(__file__).resolve(),
        ROOT / "tests/fixtures/v12_baseline.json",
        *(ROOT / "src").rglob("*.py"),
    }
    return {
        "raw_inputs": {name: file_hash(raw_directory / name) for name in sorted(input_names)},
        "formal_package": {str(p.relative_to(PACKAGE)): file_hash(p)
                           for p in sorted(PACKAGE.rglob("*")) if p.is_file()},
        "implementation": {str(p.relative_to(ROOT)): file_hash(p)
                           for p in sorted(implementation) if p.is_file()},
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw-directory", type=Path,
                    help="Directory containing the six accepted raw CSVs; otherwise use find_steam_csv()")
    args = ap.parse_args()
    raw_directory = args.raw_directory.expanduser().resolve() if args.raw_directory else find_steam_csv().parent
    if not raw_directory.is_dir():
        raise FileNotFoundError(f"Raw input directory does not exist: {raw_directory}")
    manifest = strict_json_loads((PACKAGE / "manifest/manifest.json").read_text())
    before = protected_snapshot(raw_directory, manifest["inputs"])
    started = datetime.now(timezone.utc).isoformat()
    output = ROOT / "outputs/data_eda" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    output.mkdir(parents=True, exist_ok=False)
    (output / "tables").mkdir()
    (output / "figures").mkdir()
    write_json(output / "protection_before.json", before)
    checks = []

    def check(name, ok, evidence):
        checks.append(dict(name=name, status="PASS" if bool(ok) else "FAIL", evidence=evidence))
        if not ok:
            write_json(output / "failed_checks.json", checks)
            raise AssertionError(name)

    consumer = verify_package(PACKAGE, require_real=True)
    check("physical_READY_chain", consumer["accepted_for_formal_handoff"], consumer)
    sealed = strict_json_loads((PACKAGE / "manifest/design_contract_snapshot.json").read_text())
    check("config_sha_and_design", sealed["config_sha256"] == file_hash(ROOT / "config.py")
          and sealed["design"] == json.loads(json.dumps(config.design_contract())), sealed["config_sha256"])
    check("accepted_six_input_hashes", len(manifest["inputs"]) == 6
          and all(before["raw_inputs"][n] == v["sha256"] for n, v in manifest["inputs"].items()),
          {n: v["sha256"] for n, v in manifest["inputs"].items()})
    expected_package_files = set(manifest["files"]) | {
        "manifest/manifest.json", *manifest["control_files"].values(),
    }
    check("relocated_formal_package_inventory", set(before["formal_package"]) == expected_package_files
          and len(expected_package_files) == 21,
          {"files": len(before["formal_package"]), "candidate_tree_required": False})
    schema = strict_json_loads((PACKAGE / "manifest/handoff_schema.json").read_text())
    with (PACKAGE / "manifest/field_dictionary.csv").open(encoding="utf-8", newline="") as f:
        definitions = {(r["file"], r["column"]): r for r in csv.DictReader(f)}

    def load(name):
        logical = f"handoff/{name}.csv"
        return pd.DataFrame(read_table(PACKAGE / logical, schema["files"][logical]["columns"], definitions, logical))

    x, y, meta, states, cuts = [load(n) for n in ("x_primary", "y_label", "keys_meta", "x_entity_states", "year_cutoffs")]
    check("exact_primary_columns", list(x.columns) == ["appid", *config.PRIMARY_FEATURE_COLUMNS], list(x.columns))
    check("developed_unique_keys", all(not t.appid.duplicated().any() for t in (x, y, states))
          and set(x.appid) == set(y.appid) == set(states.appid), len(x))
    check("all_source_records", len(meta) == manifest["statistics"]["source_records"]
          and not meta[["source_file", "source_row_no"]].duplicated().any(), len(meta))
    devmeta = meta.loc[meta.split.isin(SPLITS), ["appid", "release_year", "release_date_utc", "split"]]
    check("metadata_key_domain", set(devmeta.appid) == set(x.appid), len(devmeta))
    d = x.merge(y, on="appid", validate="one_to_one").merge(devmeta, on="appid", validate="one_to_one")
    check("split_policy", ((d.split == "train") == (d.release_year <= config.TRAIN_MAX_YEAR)).all()
          and ((d.split == "validation") == (d.release_year == config.VALIDATION_YEAR)).all()
          and ((d.split == "test") == (d.release_year == config.TEST_YEAR)).all()
          and not d.release_year.isin(config.EXCLUDED_RELEASE_YEARS).any(), config.design_contract()["split"])

    def save(name, frame):
        frame.to_csv(output / "tables" / f"{name}.csv", index=False, encoding="utf-8", lineterminator="\n")
        return frame

    def prevalence(g):
        return dict(n=len(g), positives=int(g[config.TARGET_COLUMN].sum()),
                    positive_rate=float(g[config.TARGET_COLUMN].mean()))

    population = []
    for split, g in meta.groupby("split", sort=False):
        label = d.loc[d.split == split, config.TARGET_COLUMN]
        population.append(dict(split=split, n=len(g), positives=int(label.sum()) if len(label) else None,
                               positive_rate=float(label.mean()) if len(label) else None))
    save("population_by_split", pd.DataFrame(population))
    check("split_count_manifest", d.groupby("split").size().to_dict() ==
          {s: manifest["statistics"]["dispositions"][s] for s in SPLITS},
          {s: prevalence(d.loc[d.split == s]) for s in SPLITS})
    check("population_positive_sum", int(d.hit_reviews.sum()) == manifest["statistics"]["developed_positive_sum"], int(d.hit_reviews.sum()))
    with (raw_directory / "steam.csv").open(encoding="utf-8", newline="") as f:
        raw = list(csv.DictReader(f))
    raw_by_id = {r["appid"].strip(): r for r in raw}
    check("raw_to_meta_identity", len(raw_by_id) == len(raw) == len(meta)
          and all(raw[int(r.source_row_no)-1]["appid"] == r.raw_appid for r in meta.itertuples()), len(raw))
    check("official_ratings_exact_raw", all(int(raw_by_id[r.appid]["positive_ratings"]) == r.positive_ratings
          and int(raw_by_id[r.appid]["negative_ratings"]) == r.negative_ratings
          and r.positive_ratings + r.negative_ratings == r.total_ratings for r in y.itertuples()), len(y))
    label_ok = True
    for year, g in d.groupby("release_year"):
        cutoff = g.total_ratings.quantile(config.TARGET_QUANTILE, interpolation=config.TARGET_INTERPOLATION)
        expected = g.total_ratings.ge(cutoff) if config.TARGET_INCLUSIVE else g.total_ratings.gt(cutoff)
        c = cuts.loc[cuts.release_year == year].iloc[0]
        label_ok &= len(g) == c.cohort_n and cutoff == c.cutoff_value and int(expected.sum()) == c.positive_n
        label_ok &= np.array_equal(expected.astype(int).to_numpy(), g.hit_reviews.to_numpy())
    check("independent_full_cohort_label_reconciliation", label_ok, {"cohorts": len(cuts), "rows": len(d), "new_targets_written": False})
    years = []
    for year, g in meta.groupby("release_year", sort=True):
        a = d.loc[d.release_year == year]
        c = cuts.loc[cuts.release_year == year]
        years.append(dict(release_year=int(year), n_source=len(g), n_developed=len(a),
                          positive_n=int(a.hit_reviews.sum()) if len(a) else None,
                          positive_rate=float(a.hit_reviews.mean()) if len(a) else None,
                          cutoff=float(c.iloc[0].cutoff_value) if len(c) else None,
                          small_cohort_lt30=len(g) < 30,
                          median_ratings=float(a.total_ratings.median()) if len(a) else None,
                          p99_ratings=float(a.total_ratings.quantile(.99)) if len(a) else None))
    years = save("population_by_year", pd.DataFrame(years))
    ratings = save("ratings_summary_by_split", pd.DataFrame([dict(split=s, n=len(g), minimum=int(g.total_ratings.min()),
        median=float(g.total_ratings.median()), p90=float(g.total_ratings.quantile(.9)),
        p99=float(g.total_ratings.quantile(.99)), maximum=int(g.total_ratings.max())) for s, g in d.groupby("split")]))

    source_missing = []
    for split, g in meta.groupby("split"):
        for field in config.DATA_PARSE_POLICY["missing"]["token_fields"]:
            counts = Counter(z[field] for z in g.source_value_classes)
            for state in ("PRESENT", *config.DATA_PARSE_POLICY["missing"]["classes"]):
                source_missing.append(dict(split=split, field=field, source_class=state,
                                           n=counts[state], denominator=len(g), share=counts[state]/len(g)))
    save("source_missing_by_split", pd.DataFrame(source_missing))
    st = states.merge(devmeta[["appid", "split"]], on="appid", validate="one_to_one")
    seqstates = []
    for split, g in st.groupby("split"):
        for field in SEQ:
            for state in config.DATA_HANDOFF_POLICY["states"]:
                n = int((g[field] == state).sum())
                seqstates.append(dict(split=split, field=field, state=state, n=n, denominator=len(g), share=n/len(g)))
    save("sequence_state_by_split", pd.DataFrame(seqstates))
    st_indexed = st.set_index("appid")
    state_ok = all((r[field] is None) == (st_indexed.loc[r["appid"], field] == "S_MISSING")
                   for r in x.to_dict("records") for field in SEQ)
    check("source_missing_state_no_imputation", state_ok, "null and empty sequence remain distinct")
    calendar_ok = True
    dates = pd.to_datetime(d.release_date_utc, utc=True)
    for field, calculated in [("release_month", dates.dt.month), ("release_quarter", dates.dt.quarter), ("release_day_of_week", dates.dt.dayofweek)]:
        calendar_ok &= np.array_equal(d[field].to_numpy(), calculated.to_numpy())
    check("calendar_independent_UTC", calendar_ok, len(d))
    calendar = []
    for split, g in d.groupby("split"):
        for field, values in [("release_month", range(1,13)), ("release_quarter", range(1,5)), ("release_day_of_week", range(7))]:
            for value in values:
                n = int((g[field] == value).sum())
                calendar.append(dict(split=split, field=field, value=value, n=n, denominator=len(g), share=n/len(g)))
    cal = save("calendar_by_split", pd.DataFrame(calendar))
    save("year_month_counts", d.groupby(["release_year", "release_month"]).size().rename("n").reset_index())

    tokens = []
    for field in ("genres", "categories", "platforms"):
        for split, g in d.groupby("split"):
            counts = Counter(token for seq in g[field] for token in (seq or ()))
            for token, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
                tokens.append(dict(field=field, split=split, token=token, n=n, denominator=len(g), share=n/len(g)))
    tok = save("token_presence_by_split", pd.DataFrame(tokens))
    check("token_incidence_reconciliation", all(sum(Counter(t for seq in d.loc[d.split == s, f] for t in (seq or ())).values())
          == sum(len(seq or ()) for seq in d.loc[d.split == s, f]) for f in ("genres", "categories", "platforms") for s in SPLITS),
          "Per-game incidence, overlaps allowed; not mutually exclusive categories")
    platform = []
    for split, g in d.groupby("split"):
        for flags, sub in g.groupby(["has_windows", "has_mac", "has_linux"]):
            combo = "+".join(name for name, flag in zip(("windows", "mac", "linux"), flags) if flag) or "no_known_platform"
            platform.append(dict(split=split, combination=combo, n=len(sub), denominator=len(g), share=len(sub)/len(g)))
    plat = save("platform_combination_by_split", pd.DataFrame(platform))
    for field in ("english", "required_age", "platform_count", "category_count", "genre_count"):
        save(f"{field}_by_split", d.groupby(["split",field], dropna=False).size().rename("n").reset_index())
    changes = tok.pivot_table(index=["field","token"], columns="split", values="share", fill_value=0).reset_index()
    for s in ("validation", "test"):
        changes[s + "_minus_train_pp"] = (changes[s]-changes.train)*100
    save("token_composition_changes", changes)

    history_counts = Counter()
    logical = "handoff/history_source_membership.csv"
    with (PACKAGE / logical).open(encoding="utf-8", newline="") as f:
        for edge in csv.DictReader(f):
            history_counts[edge["target_appid"], edge["entity_kind"]] += 1
    history_ok = True
    for r in d.itertuples():
        for kind, prefix in (("developer","dev"), ("publisher","pub")):
            history_ok &= math.isclose(getattr(r, prefix+"_prior_count"), math.log1p(history_counts[r.appid, kind]), rel_tol=0, abs_tol=1e-12)
    check("history_log1p_counts_from_membership", history_ok, {"edges": sum(history_counts.values()), "targets":len(d)})
    cold = []
    for split, g in d.groupby("split"):
        no_dev, no_pub = g.dev_prior_count.eq(0), g.pub_prior_count.eq(0)
        groups = {"no_dev_prior":no_dev, "no_pub_prior":no_pub, "neither_prior":no_dev & no_pub,
                  "either_no_prior":no_dev | no_pub, "both_prior":~no_dev & ~no_pub}
        for name, mask in groups.items():
            cold.append(dict(split=split, condition=name, n=int(mask.sum()), denominator=len(g), share=float(mask.mean())))
        for field in ("developer","publisher"):
            nmissing = int(g[field].map(lambda v:v is None).sum())
            nempty = int(g[field].map(lambda v:v == ()).sum())
            cold.append(dict(split=split, condition=field+"_source_missing", n=nmissing, denominator=len(g), share=nmissing/len(g)))
            cold.append(dict(split=split, condition=field+"_nonmissing_empty", n=nempty, denominator=len(g), share=nempty/len(g)))
    cold = save("cold_start_by_split", pd.DataFrame(cold))
    check("cold_start_prior_fallback", (d.loc[d.dev_prior_count.eq(0),"dev_prior_hit_rate"] == config.HISTORY_PRIOR_MEAN).all()
          and (d.loc[d.pub_prior_count.eq(0),"pub_prior_hit_rate"] == config.HISTORY_PRIOR_MEAN).all(), config.HISTORY_PRIOR_MEAN)
    entities = []
    for field in ("developer", "publisher"):
        for split, g in d.groupby("split"):
            counts = Counter(t for seq in g[field] for t in (seq or ()))
            singletons = {t for t, n in counts.items() if n == 1}
            singleton_only = int(g[field].map(lambda v:bool(v) and all(t in singletons for t in v)).sum())
            entities.append(dict(field=field, split=split, distinct_tokens=len(counts),
                                 singleton_tokens=len(singletons), singleton_only_games=singleton_only,
                                 singleton_only_share=singleton_only/len(g), multi_entity_games=int(g[field].map(lambda v:len(v or ())>1).sum())))
    save("entity_long_tail_by_split", pd.DataFrame(entities))
    save("history_feature_summary", d.groupby("split")[list(config.HISTORY_FEATURE_COLUMNS)].agg(["min","median","max"]).reset_index().set_axis(
        ["split"]+[f"{f}_{s}" for f in config.HISTORY_FEATURE_COLUMNS for s in ("min","median","max")], axis=1))
    aux = save("auxiliary_key_coverage", load("aux_coverage"))
    # Snapshot/owners diagnostics support wording corrections only. They never join primary X.
    snapshots = []
    raw_split = dict(zip(meta.appid, meta.split))
    for scope in ("all_source", "developed", *SPLITS, "excluded"):
        g = [r for r in raw if scope == "all_source" or (scope == "developed" and raw_split[r["appid"]] in SPLITS) or raw_split[r["appid"]] == scope]
        if not g:
            continue
        zero = [r for r in g if float(r["price"]) == 0]
        marker = [r for r in zero if "Free to Play" in [t.strip() for f in ("genres","categories") for t in r[f].split(config.ENTITY_DELIMITER)]]
        snapshots.append(dict(scope=scope, n=len(g), price_zero_n=len(zero), zero_with_F2P_token=len(marker),
                              zero_without_F2P_token=len(zero)-len(marker), price_blank_n=sum(not r["price"].strip() for r in g),
                              distinct_owner_buckets=len({r["owners"] for r in g})))
    snap = save("snapshot_diagnostics_not_X", pd.DataFrame(snapshots))
    save("owners_bucket_counts_source", pd.DataFrame([dict(owners_bucket=k,n=v,denominator=len(raw),share=v/len(raw))
                                                     for k,v in Counter(r["owners"] for r in raw).most_common()]))
    toy = pd.Series([1,1,1], index=["A","B","C"])
    selected_original = toy.rank(method="first", ascending=False).le(1)
    selected_reversed = toy.iloc[::-1].rank(method="first", ascending=False).le(1)
    check("owners_first_rank_order_dependence_demonstrated", set(toy.index[selected_original]) != set(selected_reversed.index[selected_reversed]),
          {"toy_equal_values":True,"original_selected":["A"],"reversed_selected":["C"],"real_new_owners_labels_written":False})
    owner2019 = Counter(r["owners"] for r in raw if raw_split[r["appid"]] == "excluded")
    summary = dict(formal_package=str(PACKAGE.relative_to(ROOT)), design=config.DESIGN_VERSION, business_base=config.BASE_DESIGN_VERSION,
        population=population, years=years.where(pd.notna(years), None).to_dict("records"),
        cold_start=cold.to_dict("records"), snapshot_diagnostics=snap.to_dict("records"),
        missing_source_all={f:dict(Counter(z[f] for z in meta.source_value_classes)) for f in config.DATA_PARSE_POLICY["missing"]["token_fields"]},
        owner2019_buckets=dict(owner2019), auxiliary_coverage=aux.to_dict("records"),
        test_descriptive_only=True, learned_transforms=False, model_training=False, model_metrics=False,
        label_tables_not_rewritten=True, snapshot_sensitivity_interface_enabled=False,
        definitions={"token_share":"games containing token / games in split; overlapping tokens",
                     "cold_start":"no matching strictly earlier-year games in accepted union, including missing/empty entities",
                     "entity_singleton":"occurs once inside this split only, not global identity or cold start",
                     "history_count":"stored as log1p(N), NOT raw N",
                     "price_zero_without_F2P":"snapshot zero price with no explicit token; cause unknown",
                     "denominators":"main EDA developed 24862; correction appendix all-source 27075 explicitly separated"})
    # pandas represents nullable numerical report cells by NaN; convert through JSON for strict output.
    summary["years"] = json.loads(years.to_json(orient="records"))
    write_json(output / "summary.json", summary)
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":10,"axes.spines.top":False,"axes.spines.right":False,
                         "axes.titleweight":"bold","figure.facecolor":"white","savefig.facecolor":"white"})
    colors = {"train":"#315b72","validation":"#d69a35","test":"#428b77"}
    figure_paths = []

    def finish(fig, name):
        fig.tight_layout()
        for ext in ("png", "svg"):
            fig.savefig(output / "figures" / f"{name}.{ext}", dpi=160, bbox_inches="tight")
        plt.close(fig)
        figure_paths.append(name)

    fig, ax = plt.subplots(1,2,figsize=(13,4.3))
    ax[0].bar(years.release_year, years.n_source, color=[colors.get("train" if y<=config.TRAIN_MAX_YEAR else "validation" if y==config.VALIDATION_YEAR else "test" if y==config.TEST_YEAR else "excluded", "#c5c9ca") for y in years.release_year])
    ax[0].set(title="Source release years (2019 excluded)",xlabel="Release year",ylabel="Games")
    a = years.loc[years.n_developed>0]
    ax[1].plot(a.release_year,a.cutoff,marker="o",color=colors["train"])
    ax[1].set(yscale="log",title="Accepted within-year q90 cutoffs",xlabel="Release year",ylabel="Total ratings (log scale)")
    finish(fig,"01_population_and_cutoffs")
    fig, ax = plt.subplots(1,2,figsize=(13,4.5))
    for axis,field in zip(ax,("genres","categories")):
        sub = tok.loc[tok.field==field]
        top = sub.groupby("token").n.sum().nlargest(10).index[::-1]
        p = sub.pivot(index="token",columns="split",values="share").reindex(top).fillna(0)
        for i,s in enumerate(SPLITS):
            axis.barh(np.arange(len(top))+(i-1)*.24,p[s]*100,height=.23,label=s,color=colors[s])
        axis.set(yticks=np.arange(len(top)),yticklabels=top,xlabel="Games containing token (%)",title=field.capitalize()+" presence; overlaps allowed")
    ax[0].legend(loc="lower right",fontsize=8)
    finish(fig,"02_genres_and_categories")
    fig, ax = plt.subplots(1,2,figsize=(13,4.3))
    for i,s in enumerate(SPLITS):
        sub = plat.loc[plat.split==s].set_index("combination").share
        order = plat.groupby("combination").n.sum().sort_values(ascending=False).index
        ax[0].bar(np.arange(len(order))+(i-1)*.24,sub.reindex(order,fill_value=0)*100,width=.23,label=s,color=colors[s])
        sub = cal.loc[(cal.split==s)&(cal.field=="release_month")]
        ax[1].plot(sub.value,sub.share*100,marker="o",label=s,color=colors[s])
    ax[0].set(xticks=np.arange(len(order)),xticklabels=order,ylabel="Games (%)",title="Known platform combinations")
    ax[0].tick_params(axis="x",rotation=20)
    ax[1].set(xticks=range(1,13),xlabel="UTC release month",ylabel="Within-split games (%)",title="Release-month composition; unequal year mix")
    ax[1].legend()
    finish(fig,"03_platforms_and_calendar")
    fig, ax = plt.subplots(1,2,figsize=(13,4.3))
    order = ("no_dev_prior","no_pub_prior","neither_prior")
    for i,s in enumerate(SPLITS):
        sub = cold.loc[cold.split==s].set_index("condition")
        ax[0].bar(np.arange(3)+(i-1)*.24,sub.loc[list(order),"share"]*100,width=.23,label=s,color=colors[s])
    ax[0].set(xticks=range(3),xticklabels=["No developer prior","No publisher prior","Neither prior"],ylabel="Games (%)",title="No earlier-year union history (window A)")
    ax[0].legend(fontsize=8)
    fields = ("developer","publisher")
    for i,s in enumerate(SPLITS):
        n = [int(st.loc[st.split==s,f].eq("S_MISSING").sum()) for f in fields]
        ax[1].bar(np.arange(2)+(i-1)*.24,n,width=.23,color=colors[s],label=s)
    ax[1].set(xticks=range(2),xticklabels=fields,ylabel="Games with source missing",title="Missing entities: empty + whitespace + declared")
    finish(fig,"04_history_and_missing")
    fig, ax = plt.subplots(1,2,figsize=(13,4.3))
    values = [d.loc[d.split==s,"total_ratings"].to_numpy() for s in SPLITS]
    ax[0].boxplot(values,tick_labels=SPLITS,showfliers=False,medianprops={"color":"#d69a35"})
    ax[0].set(yscale="log",ylabel="Total ratings (log scale)",title="Snapshot ratings distributions; outliers hidden")
    diagnostic = snap.loc[snap.scope=="all_source"].iloc[0]
    ax[1].bar(["Zero + F2P token","Zero, no F2P token"],[diagnostic.zero_with_F2P_token,diagnostic.zero_without_F2P_token],color=["#428b77","#d69a35"])
    ax[1].set(ylabel="Source games",title="Zero-price annotation only; cause unknown")
    for i,n in enumerate([diagnostic.zero_with_F2P_token,diagnostic.zero_without_F2P_token]):
        ax[1].text(i,n+20,str(n),ha="center")
    finish(fig,"05_snapshot_diagnostics")
    after = protected_snapshot(raw_directory, manifest["inputs"])
    protected_counts = {group: len(files) for group, files in before.items()}
    check("current_raw_package_implementation_unchanged", before == after,
          {"protected_files": sum(protected_counts.values()), "groups": protected_counts,
           "snapshot_created_for_this_execution": True})
    write_json(output / "protection_after.json", after)
    inventory = {str(p.relative_to(output)):file_hash(p) for p in sorted(output.rglob("*")) if p.is_file()}
    write_json(output / "validation.json", dict(overall="pass",scope="descriptive_EDA_only",checks=checks,
        verification_version="relocated-eda/v1", historical_validation_replaced=False,
        model_training=False, protected_counts=protected_counts,
        started_utc=started,finished_utc=datetime.now(timezone.utc).isoformat(), script_sha256=file_hash(Path(__file__)),
        config_sha256=file_hash(ROOT/"config.py"),runtime={"python":sys.version.split()[0],"pandas":pd.__version__,"numpy":np.__version__,"matplotlib":matplotlib.__version__},
        tables=sum(p.suffix==".csv" for p in (output/"tables").iterdir()),figures=figure_paths,output_files=inventory))
    print(json.dumps({"directory":str(output.relative_to(ROOT)),"checks":len(checks),"overall":"pass","tables":len(list((output/"tables").iterdir())),"figures":len(figure_paths)},ensure_ascii=False))


if __name__ == "__main__":
    main()
