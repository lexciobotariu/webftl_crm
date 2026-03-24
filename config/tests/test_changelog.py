from django.test import TestCase

from config.changelog import parse_changelog


class ParseChangelogTest(TestCase):
    def test_parses_single_version(self):
        md = """# Changelog

## [0.1.0] - 2025-01-27

### Added
- Feature one
- Feature two
"""
        result = parse_changelog(md)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['version'], '0.1.0')
        self.assertEqual(result[0]['date'], '2025-01-27')
        self.assertEqual(result[0]['sections'], [
            {'name': 'Added', 'items': ['Feature one', 'Feature two']}
        ])

    def test_parses_multiple_versions(self):
        md = """# Changelog

## [0.1.2] - 2026-01-29

### Fixed
- Bug fix one

### Changed
- Refactor something

## [0.1.1] - 2026-01-27

### Changed
- Style update

## [0.1.0] - 2025-01-27

### Added
- Initial release
"""
        result = parse_changelog(md)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]['version'], '0.1.2')
        self.assertEqual(result[1]['version'], '0.1.1')
        self.assertEqual(result[2]['version'], '0.1.0')
        self.assertEqual(len(result[0]['sections']), 2)
        self.assertEqual(result[0]['sections'][0]['name'], 'Fixed')
        self.assertEqual(result[0]['sections'][1]['name'], 'Changed')

    def test_empty_changelog(self):
        md = """# Changelog

All notable changes to this project will be documented in this file.
"""
        result = parse_changelog(md)
        self.assertEqual(result, [])

    def test_handles_missing_date(self):
        md = """# Changelog

## [Unreleased]

### Added
- Work in progress
"""
        result = parse_changelog(md)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['version'], 'Unreleased')
        self.assertEqual(result[0]['date'], '')
