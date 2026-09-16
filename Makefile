.PHONY: sanity-ignore-sync sanity-ignore-check ansible-lint

sanity-ignore-sync:
	./scripts/sync-sanity-ignore.sh

sanity-ignore-check:
	@cmp -s tests/sanity/ignore-2.20.txt tests/sanity/ignore-2.16.txt || \
		(echo "Sanity ignore files are out of sync. Run: make sanity-ignore-sync" && exit 1)

ansible-lint:
	./scripts/run_ansible_lint.sh -c .ansible-lint --offline --nocolor -f codeclimate playbooks/deploy_openshift_phase1.yaml playbooks/deploy_openshift_phase2.yaml