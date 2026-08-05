# ARCHIVED 2026-07-11 by Batman's order: the v2 extractive draft (Borda openers +
# MMR + lambda sweep) and the Ollama polish are NOT production-ready yet - still in
# development. Production's Review tab shows only the deterministic v1 scaffold.
#
# This is the exact UI block that used to live in app.py under `with tab_review:`.
# The engine functions it calls are STILL in the repo (we keep improving them):
#   - review.py: review_lambda-wrapped recommend_lambda, review_v2-wrapped
#     draft_review_v2, textrank_sentences, mmr_sentences
#   - polish.py: available_models, polish_draft
# app.py also still defines the cached wrappers review_lambda() and review_v2().
#
# TO RESTORE into production: paste the body below back inside `with tab_review:`
# in app.py (after the scaffold), and re-add the `md_v2` reference used by polish.
# Last commit that shipped this in the UI: see git log around 2026-07-11.

# ----------------------------------------------------------------------------------
#     st.caption("Review draft v2 - **extractive**: every sentence below is quoted "
#                "verbatim from a corpus abstract and carries its citation [n], so "
#                "nothing can be hallucinated. Sections open with the sentence both "
#                "rankers agree on most (Borda); support sentences are typical but "
#                "diverse (MMR). † = centroid and TextRank independently agree.")
#     density = st.slider(
#         "Sentences per subtopic", min_value=2, max_value=5, value=3,
#         help="1 opener + N-1 supporting sentences per section.")
#     with st.spinner("Choosing the diversity knob from this corpus (lambda sweep)..."):
#         lam, sweep = review_lambda(mcs, years, SLUG, DATA_VERSION)
#     with st.spinner("Assembling the draft (selecting real sentences)..."):
#         md_v2, bib_v2, refs_v2 = review_v2(mcs, years, SLUG, DATA_VERSION,
#                                            support_n=density - 1, lam=lam)
#     st.caption(f"Diversity lambda = {lam} - not a default: swept on THIS corpus, "
#                "keeping the most diversity that preserves 99% of relevance.")
#     with st.expander("How lambda was chosen (the sweep)", icon=":material/tune:"):
#         st.dataframe(sweep, hide_index=True)
#
#     d1, d2 = st.columns(2)
#     d1.download_button("Download draft v2 (.md)", data=md_v2,
#                        file_name="froth_review_v2.md", mime="text/markdown",
#                        icon=":material/download:")
#     d2.download_button("Download references (.bib)", data=bib_v2,
#                        file_name="froth_review_v2.bib", mime="text/plain",
#                        icon=":material/menu_book:")
#
#     with st.container(height=560, border=True):
#         st.markdown(md_v2)
#
#     if len(refs_v2):
#         pick = st.selectbox(
#             "Inspect a cited paper",
#             options=refs_v2["n"].tolist(),
#             format_func=lambda n: f"[{n}] "
#             f"{refs_v2[refs_v2['n'] == n]['title'].iloc[0][:90]}",
#         )
#         title_pick = refs_v2[refs_v2["n"] == pick]["title"].iloc[0]
#         match = tm[tm["title"] == title_pick]
#         if len(match):
#             paper_detail_panel(match.iloc[0], tm, key="review")
#
#     with st.expander("Polish with a local LLM (optional - citations verified)",
#                      icon=":material/auto_fix_high:"):
#         ollama_models = polish_mod.available_models()
#         if not ollama_models:
#             st.markdown(
#                 "The extractive draft above is the truth-safe default. If you want "
#                 "smoother prose, Froth can ask a **local** model (Ollama) to rewrite "
#                 "each paragraph - and every citation [n] is verified to survive "
#                 "exactly; sections that fail verification keep their original.\n\n"
#                 "Ollama is **not running** on this machine. One-time setup (~5 GB "
#                 "model, free, private, offline): see "
#                 "[docs/OLLAMA_SETUP.md](https://ollama.com/download) - install, then "
#                 "`ollama pull llama3.1:8b` and reload this page.")
#         else:
#             model_pick = st.selectbox("Local model", ollama_models)
#             if st.button("Polish the draft", icon=":material/auto_fix_high:"):
#                 with st.spinner("Rewriting section by section (citations verified)..."):
#                     polished_md, n_ok, n_kept = polish_mod.polish_draft(md_v2,
#                                                                         model_pick)
#                 st.session_state["polished_md"] = polished_md
#                 st.session_state["polish_stats"] = (n_ok, n_kept)
#             if st.session_state.get("polished_md"):
#                 n_ok, n_kept = st.session_state["polish_stats"]
#                 st.caption(f"{n_ok} sections polished · {n_kept} kept extractive "
#                            "(verification failed or nothing to improve). The "
#                            "extractive original above stays the default.")
#                 st.download_button("Download polished draft (.md)",
#                                    data=st.session_state["polished_md"],
#                                    file_name="froth_review_v2_polished.md",
#                                    mime="text/markdown", icon=":material/download:")
#                 with st.container(height=380, border=True):
#                     st.markdown(st.session_state["polished_md"])
