// Registers the jest-dom matchers (toBeVisible, toHaveAttribute, …) with Vitest's
// expect. This file existing is what turned the installed-but-unused Testing Library
// stack into a working one — the deps sat in package.json for months with no test
// environment to run in.
import '@testing-library/jest-dom/vitest';
