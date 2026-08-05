# ARCHIVED 2026-07-11 by Batman's order: the Gaps view confused users and is OUT
# of production (it was a tab, then briefly a section inside Review). This is the
# full section code, ready to paste back at the end of app.py if it ever returns.
# Last production commit that contained it: c516aa1. The engine (froth/gaps.py,
# find_gaps, draft_review) is UNTOUCHED and still powers the v1-draft comparison.

with tab_review:
    st.subheader("Research gaps", divider="violet")
    gap_table, draft_text = gaps_and_draft(mcs, years, SLUG, DATA_VERSION)

    st.caption("Research opportunities, measured on YOUR corpus - the tool proposes with "
               "evidence; only the expert can tell an unexplored mine from a barren desert.")

    # Plain-language cards (Batman: the raw score table told him nothing - and he BUILT it).
    GAP_MEANING = {
        "silo": (":material/wall:", "Silo - the best kind of gap",
                 "These two subtopics study SIMILAR things but barely CITE each other: "
                 "two communities working back-to-back. Whoever connects them says "
                 "something new."),
        "scarce_bridge": (":material/link_off:", "Scarce bridge",
                          "Only a handful of papers connect these two related subtopics - "
                          "there is room for more travelers on this route."),
        "dormant": (":material/bedtime:", "Dormant subtopic",
                    "Its newest papers are getting old: nobody has revisited this area "
                    "with modern methods lately."),
        "sparse_zone (experimental)": (":material/help_center:", "Empty zone (experimental)",
                                       "Few papers live between these two related areas. "
                                       "Weakest signal of the four: emptiness can mean "
                                       "unexplored... or simply barren."),
    }
    GAP_THRESHOLD = {"silo": 0.08, "scarce_bridge": 0.03, "dormant": 0.25,
                     "sparse_zone (experimental)": 0.08}

    for gtype, (icon, name, meaning) in GAP_MEANING.items():
        part = gap_table[gap_table["type"] == gtype]
        strong = part[part["score"] >= GAP_THRESHOLD[gtype]]
        if gtype == "dormant" and strong.empty:
            st.success("No dormant subtopics - every area of this field has recent "
                       "papers. (That's good news, not a missing gap.)",
                       icon=":material/local_fire_department:")
            continue
        # Always show the best candidates; the threshold only grades the signal -
        # fixed cutoffs hid everything at some granularities (magic numbers strike again).
        for _, r in part.head(2).iterrows():
            grade = ("strong signal" if r["score"] >= GAP_THRESHOLD[gtype]
                     else "weak signal - read with skepticism")
            with st.container(border=True):
                st.markdown(f"{icon} **{name}**")
                st.markdown(f"**{r['where'].replace('<->', '↔')}**")
                st.caption(meaning)
                st.caption(f"Evidence: {r['evidence']} · {grade} ({r['score']:.2f})")

    with st.expander("Raw data (every candidate and score)", icon=":material/table:"):
        st.dataframe(gap_table, hide_index=True,
                     column_config={"score": st.column_config.NumberColumn(format="%.3f")})

    # THE semantic map lives here (and only here): positions = meaning, silos = geography.
    show_gap_lines = st.toggle("Show measured gap lines (silos)", value=True,
                               help="Dashed red lines between subtopics that are "
                                    "semantically close but barely cite each other.")
    if show_gap_lines:
        fig = visualize.gap_overlay_figure(tm, gap_table, size_by_citations=size_by_cites,
                                           hide_noise=hide_noise)
    else:
        fig = visualize.bubble_figure(tm, size_by_citations=size_by_cites,
                                      hide_noise=hide_noise)
    gaps_event = st.plotly_chart(fig, theme=None, on_select="rerun",
                                 selection_mode="points", key="gaps_select")
    st.caption("Positions carry meaning here (semantic distance, UMAP). Hover for details; "
               "click a point to inspect it. Red dashed lines = under-cited frontiers.")
    row = _selected_row(gaps_event, tm)
    if row is not None:
        paper_detail_panel(row, tm, key="gaps")

    st.download_button(
        "Download review draft (.md)", data=draft_text,
        file_name="froth_review_draft.md", mime="text/markdown",
        icon=":material/download:",
    )
    with st.expander("Preview the draft", icon=":material/description:"):
        st.markdown(draft_text)
