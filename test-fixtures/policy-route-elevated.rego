package ods.policy

# Self-test fixture: always allow, always route to "elevated" so the
# review-tier plumbing can be asserted deterministically regardless of what
# the test diff contains.
default allow := true

review_tier := "elevated"
