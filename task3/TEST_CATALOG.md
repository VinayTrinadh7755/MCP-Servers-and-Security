# Task 3 Test Catalog

This catalog is generated from `pytest task3/tests --collect-only -q` after the submission validation remediation. Test names are the one-line behavior descriptions.

## task3/tests/test_live_concurrency.py (1)

- `test_fifty_concurrent_mixed_and_one_character_card_streams_are_isolated` — fifty concurrent mixed and one character card streams are isolated.

## task3/tests/test_performance.py (2)

- `test_benchmark_reports_medians_and_plausible_metrics` — benchmark reports medians and plausible metrics.
- `test_pattern_like_work_scales_without_quadratic_blowup` — pattern like work scales without quadratic blowup.

## task3/tests/test_phase0.py (16)

- `test_card_fixture_defaults_support_one_character_frames` — card fixture defaults support one character frames.
- `test_provider_emits_openai_sse_and_terminal_sentinel[plain]` — provider emits openai sse and terminal sentinel[plain].
- `test_provider_emits_openai_sse_and_terminal_sentinel[email]` — provider emits openai sse and terminal sentinel[email].
- `test_provider_emits_openai_sse_and_terminal_sentinel[ssn]` — provider emits openai sse and terminal sentinel[ssn].
- `test_provider_emits_openai_sse_and_terminal_sentinel[card]` — provider emits openai sse and terminal sentinel[card].
- `test_provider_emits_openai_sse_and_terminal_sentinel[card-split-one-char]` — provider emits openai sse and terminal sentinel[card-split-one-char].
- `test_provider_emits_openai_sse_and_terminal_sentinel[mixed]` — provider emits openai sse and terminal sentinel[mixed].
- `test_provider_emits_openai_sse_and_terminal_sentinel[pii-end]` — provider emits openai sse and terminal sentinel[pii-end].
- `test_provider_emits_openai_sse_and_terminal_sentinel[single]` — provider emits openai sse and terminal sentinel[single].
- `test_provider_emits_openai_sse_and_terminal_sentinel[empty]` — provider emits openai sse and terminal sentinel[empty].
- `test_provider_unknown_fixture_falls_back_safely` — provider unknown fixture falls back safely.
- `test_single_fixture_has_exactly_one_content_delta` — single fixture has exactly one content delta.
- `test_card_fixture_defaults_to_one_character_content_deltas` — card fixture defaults to one character content deltas.
- `test_malformed_fixture_emits_deliberately_invalid_data_frame` — malformed fixture emits deliberately invalid data frame.
- `test_hang_fixture_can_be_shortened_for_deterministic_validation` — hang fixture can be shortened for deterministic validation.
- `test_disconnect_fixture_raises_after_partial_body_in_process` — disconnect fixture raises after partial body in process.

## task3/tests/test_redactor.py (50)

- `test_each_pattern_is_redacted_when_fed_whole[email-ada.lovelace@example.com]` — each pattern is redacted when fed whole[email-ada.lovelace@example.com].
- `test_each_pattern_is_redacted_when_fed_whole[ssn-123-45-6789]` — each pattern is redacted when fed whole[ssn-123-45-6789].
- `test_each_pattern_is_redacted_when_fed_whole[card-4111-1111-1111-1111]` — each pattern is redacted when fed whole[card-4111-1111-1111-1111].
- `test_each_pattern_is_redacted_when_fed_whole[card-4111 1111 1111 1111]` — each pattern is redacted when fed whole[card-4111 1111 1111 1111].
- `test_each_pattern_is_redacted_when_fed_whole[card-4111111111111111]` — each pattern is redacted when fed whole[card-4111111111111111].
- `test_one_character_at_a_time_equals_one_call[email-ada.lovelace@example.com]` — one character at a time equals one call[email-ada.lovelace@example.com].
- `test_one_character_at_a_time_equals_one_call[ssn-123-45-6789]` — one character at a time equals one call[ssn-123-45-6789].
- `test_one_character_at_a_time_equals_one_call[card-4111-1111-1111-1111]` — one character at a time equals one call[card-4111-1111-1111-1111].
- `test_one_character_at_a_time_equals_one_call[card-4111 1111 1111 1111]` — one character at a time equals one call[card-4111 1111 1111 1111].
- `test_one_character_at_a_time_equals_one_call[card-4111111111111111]` — one character at a time equals one call[card-4111111111111111].
- `test_every_two_chunk_split_equals_one_call[email-ada.lovelace@example.com]` — every two chunk split equals one call[email-ada.lovelace@example.com].
- `test_every_two_chunk_split_equals_one_call[ssn-123-45-6789]` — every two chunk split equals one call[ssn-123-45-6789].
- `test_every_two_chunk_split_equals_one_call[card-4111-1111-1111-1111]` — every two chunk split equals one call[card-4111-1111-1111-1111].
- `test_every_two_chunk_split_equals_one_call[card-4111 1111 1111 1111]` — every two chunk split equals one call[card-4111 1111 1111 1111].
- `test_every_two_chunk_split_equals_one_call[card-4111111111111111]` — every two chunk split equals one call[card-4111111111111111].
- `test_card_one_character_at_a_time_has_exact_whole_output` — card one character at a time has exact whole output.
- `test_every_supported_card_length_and_separator[-13]` — every supported card length and separator[-13].
- `test_every_supported_card_length_and_separator[-14]` — every supported card length and separator[-14].
- `test_every_supported_card_length_and_separator[-15]` — every supported card length and separator[-15].
- `test_every_supported_card_length_and_separator[-16]` — every supported card length and separator[-16].
- `test_every_supported_card_length_and_separator[-17]` — every supported card length and separator[-17].
- `test_every_supported_card_length_and_separator[-18]` — every supported card length and separator[-18].
- `test_every_supported_card_length_and_separator[-19]` — every supported card length and separator[-19].
- `test_every_supported_card_length_and_separator[--13]` — every supported card length and separator[--13].
- `test_every_supported_card_length_and_separator[--14]` — every supported card length and separator[--14].
- `test_every_supported_card_length_and_separator[--15]` — every supported card length and separator[--15].
- `test_every_supported_card_length_and_separator[--16]` — every supported card length and separator[--16].
- `test_every_supported_card_length_and_separator[--17]` — every supported card length and separator[--17].
- `test_every_supported_card_length_and_separator[--18]` — every supported card length and separator[--18].
- `test_every_supported_card_length_and_separator[--19]` — every supported card length and separator[--19].
- `test_every_supported_card_length_and_separator[ -13]` — every supported card length and separator[ -13].
- `test_every_supported_card_length_and_separator[ -14]` — every supported card length and separator[ -14].
- `test_every_supported_card_length_and_separator[ -15]` — every supported card length and separator[ -15].
- `test_every_supported_card_length_and_separator[ -16]` — every supported card length and separator[ -16].
- `test_every_supported_card_length_and_separator[ -17]` — every supported card length and separator[ -17].
- `test_every_supported_card_length_and_separator[ -18]` — every supported card length and separator[ -18].
- `test_every_supported_card_length_and_separator[ -19]` — every supported card length and separator[ -19].
- `test_pii_at_start_and_at_end_is_caught_by_flush` — pii at start and at end is caught by flush.
- `test_adjacent_pii_items_are_both_redacted` — adjacent pii items are both redacted.
- `test_clean_or_near_match_text_is_byte_identical[No private data appears in this document.]` — clean or near match text is byte identical[No private data appears in this document.].
- `test_clean_or_near_match_text_is_byte_identical[123456789012]` — clean or near match text is byte identical[123456789012].
- `test_clean_or_near_match_text_is_byte_identical[12345678901234567890]` — clean or near match text is byte identical[12345678901234567890].
- `test_clean_or_near_match_text_is_byte_identical[123-45-678]` — clean or near match text is byte identical[123-45-678].
- `test_clean_or_near_match_text_is_byte_identical[name@example]` — clean or near match text is byte identical[name@example].
- `test_clean_or_near_match_text_is_byte_identical[The literal marker [REDACTED] remains unchanged.]` — clean or near match text is byte identical[The literal marker [REDACTED] remains unchanged.].
- `test_mixed_patterns_and_counts` — mixed patterns and counts.
- `test_memory_is_bounded_and_clean_prefix_is_emitted` — memory is bounded and clean prefix is emitted.
- `test_long_clean_document_is_identical_during_incremental_emission` — long clean document is identical during incremental emission.
- `test_flush_clears_buffer_and_instance_can_be_reused` — flush clears buffer and instance can be reused.
- `test_feed_rejects_non_string_input` — feed rejects non string input.

## task3/tests/test_sse.py (29)

- `test_decoder_handles_every_utf8_byte_boundary_and_crlf` — decoder handles every utf8 byte boundary and crlf.
- `test_pii_split_one_character_per_sse_frame[ada@example.com-[REDACTED]-email]` — pii split one character per sse frame[ada@example.com-[REDACTED]-email].
- `test_pii_split_one_character_per_sse_frame[123-45-6789-[REDACTED]-ssn]` — pii split one character per sse frame[123-45-6789-[REDACTED]-ssn].
- `test_pii_split_one_character_per_sse_frame[4111-1111-1111-1111-[REDACTED]-card]` — pii split one character per sse frame[4111-1111-1111-1111-[REDACTED]-card].
- `test_clean_content_is_byte_identical_when_assembled` — clean content is byte identical when assembled.
- `test_pii_at_end_is_flushed_before_finish_and_sentinel` — pii at end is flushed before finish and sentinel.
- `test_missing_upstream_sentinel_is_added_once` — missing upstream sentinel is added once.
- `test_usage_frame_is_preserved_and_terminal_is_not_duplicated` — usage frame is preserved and terminal is not duplicated.
- `test_sse_comment_and_event_only_fields_are_preserved` — sse comment and event only fields are preserved.
- `test_content_after_done_is_discarded` — content after done is discarded.
- `test_empty_content_metadata_frame_is_preserved` — empty content metadata frame is preserved.
- `test_malformed_frames_fail_closed[data: {not-json}]` — malformed frames fail closed[data: {not-json}].
- `test_malformed_frames_fail_closed[data: []]` — malformed frames fail closed[data: []].
- `test_malformed_frames_fail_closed[data: {"choices":{}}]` — malformed frames fail closed[data: {"choices":{}}].
- `test_malformed_frames_fail_closed[data: {"choices":[{"delta":{"content":"safe"}},{"delta":{"content":"ada@example.com"}}]}]` — malformed frames fail closed[data: {"choices":[{"delta":{"content":"safe"}},{"delta":{"content":"ada@example.com"}}]}].
- `test_malformed_frames_fail_closed[data: {"choices":[{"delta":7}]}]` — malformed frames fail closed[data: {"choices":[{"delta":7}]}].
- `test_malformed_frames_fail_closed[data: {"choices":[{"delta":{"content":7}}]}]` — malformed frames fail closed[data: {"choices":[{"delta":{"content":7}}]}].
- `test_request_scoped_instances_cannot_mix_tenants` — request scoped instances cannot mix tenants.
- `test_closing_downstream_generator_closes_upstream_context` — closing downstream generator closes upstream context.
- `test_downstream_cancellation_propagates_and_closes_upstream` — downstream cancellation propagates and closes upstream.
- `test_provider_key_is_server_side_and_sent_as_bearer` — provider key is server side and sent as bearer.
- `test_gateway_converts_malformed_upstream_to_error_and_done` — gateway converts malformed upstream to error and done.
- `test_invalid_stream_controls_are_rejected_before_forwarding[not-json-valid JSON]` — invalid stream controls are rejected before forwarding[not-json-valid JSON].
- `test_invalid_stream_controls_are_rejected_before_forwarding[[]-JSON object]` — invalid stream controls are rejected before forwarding[[]-JSON object].
- `test_invalid_stream_controls_are_rejected_before_forwarding[{"stream":false}-requires stream=true]` — invalid stream controls are rejected before forwarding[{"stream":false}-requires stream=true].
- `test_invalid_stream_controls_are_rejected_before_forwarding[{"stream":"true"}-stream must be a boolean]` — invalid stream controls are rejected before forwarding[{"stream":"true"}-stream must be a boolean].
- `test_invalid_stream_controls_are_rejected_before_forwarding[{"stream":true,"n":2}-exactly one choice]` — invalid stream controls are rejected before forwarding[{"stream":true,"n":2}-exactly one choice].
- `test_unknown_request_fields_are_preserved_and_stream_is_forced_true` — unknown request fields are preserved and stream is forced true.
- `test_non_sse_provider_content_type_fails_closed` — non sse provider content type fails closed.

## task3/tests/test_streaming.py (3)

- `test_one_megabyte_single_token_keeps_buffer_bounded` — one megabyte single token keeps buffer bounded.
- `test_ten_thousand_one_character_frames_remain_bounded_and_exact` — ten thousand one character frames remain bounded and exact.
- `test_repeated_pattern_like_input_does_not_accumulate` — repeated pattern like input does not accumulate.

## Total

101 collected test node IDs.

