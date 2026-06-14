# Chapter 1

Introduction paragraph for the first chapter. It mentions MarkdownIntro so the
test can locate this top-level block.

## Section 1.1

This is the content of section one point one. It contains the marker
MarkdownSection11 used by the parser test to check the section breadcrumb.

# Chapter 2

## Section 2.1

This is the content of section two point one and it contains the unique marker
MarkdownSection21. The retrieval system will later split long sections like this
one into several overlapping chunks, so the paragraph is intentionally a little
longer than a single sentence. It keeps discussing the same topic across a few
sentences to make sure the section breadcrumb is preserved on every chunk that is
produced from this block during the chunking phase of the ingestion pipeline.
