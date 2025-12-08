# Baseline Screenshots

This directory contains baseline screenshots used for comparison in automated tests.

## Screenshots

- `IB_API_PAPER-screenshot.png` - Baseline for IB API + Paper Trading configuration
- `FIX_LIVE-screenshot.png` - Baseline for FIX + Live Trading configuration

## Setting Up Baselines

### Automatic Setup (Recommended)

1. Run the Test Automation workflow in GitHub Actions
2. After it completes successfully, the "Setup Baseline Screenshots" workflow will automatically download the screenshots and commit them to this directory

### Manual Setup

1. Run the Test Automation workflow
2. Download the `automation-test-screenshots-*` artifacts from the workflow run
3. Copy the screenshots to this directory with the correct filenames:
   - `IB_API_PAPER-screenshot.png`
   - `FIX_LIVE-screenshot.png`
4. Commit and push the changes

## Comparison Thresholds

Screenshots are considered similar if:
- Mean pixel difference < 5% (threshold: 0.05)
- Different pixels < 5%

If screenshots differ significantly, the test will fail to alert you of visual regressions.
