.PHONY: test deep scan

check:
	@pnpm audit
	@pnpm prettier
	@pnpm lint
	@pre-commit run --all-files

check-all: check
	@(cd case-manager && make check)

fix:
	@pnpm prettier-fix
	@pnpm lint-fix

fix-all: fix
	@(cd case-manager && make fix)

install:
	@pnpm install --frozen-lockfile

test:
	@pnpm test
