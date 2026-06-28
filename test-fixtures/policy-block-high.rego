package ods.policy

default allow := true

# Block any high or critical severity issue — including findings ingested from
# an external SARIF analyzer. Used by the self-test to prove SARIF findings
# reach the policy gate.
deny[msg] {
	issue := input.issues[_]
	issue.severity == "high"
	msg := sprintf("%s at %s:%d", [issue.rule, issue.file, issue.line])
}

deny[msg] {
	issue := input.issues[_]
	issue.severity == "critical"
	msg := sprintf("%s at %s:%d", [issue.rule, issue.file, issue.line])
}
