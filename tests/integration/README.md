# Integration tests

These tests make real requests to the Apify API (as opposed to unit tests that mock API calls), but they do not build or deploy Actors on the platform. They can be fully debugged locally and are faster than E2E tests.

Preferably try to write integration tests on this level if possible. Only write E2E tests (see `tests/e2e/`) when you need to test something that can only be tested by building and running an Actor on the platform.

## Running

```bash
# Set the API token
export APIFY_TEST_USER_API_TOKEN=<your-token>

# Run the tests
uv run poe integration-tests
```

If you want to run the tests against a different environment than the main Apify platform, set the `APIFY_INTEGRATION_TESTS_API_URL` environment variable to the right URL.
