# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-03-24

### Features
- Add status board visibility toggle — managers can hide status columns from the kanban board to reduce clutter
- Hidden tasks badge shows count of tasks in non-visible columns on the board header
- New tasks default to the first visible status when created without specifying one

### Fixes
- Support both Keep a Changelog and release skill section labels in changelog template

## [0.2.0] - 2026-03-24

### Features
- Add unified notes table on client profile showing notes from client and all its projects
- Add changelog page with parsed version history accessible from sidebar
- Add Iconify integration for brand icons (GitHub)

### Fixes
- Remove unreachable duplicate URL route in clients app
- Fix missing GitHub icon on project overview page (Lucide dropped brand icons)

## [0.1.2] - 2026-01-29

### Fixed
- Preserve instance values when editing salary month forms (empty drawer bug)
- Make PaymentForm initialization explicit for new records only
- Resolve HTMX/Alpine.js conflict in edit buttons using htmx.ajax() workaround

### Changed
- Add service layer structure for salaries app
- Refactor views to use service layer (thin controllers pattern)
- Add comprehensive service layer tests

## [0.1.1] - 2026-01-27

### Changed
- Standardize drawer button styling across all modules
- Remove `flex-1` from primary buttons for compact layout
- Add gray transparent background with subtle border to Cancel buttons
- Change notes module from purple to accent color for consistency

## [0.1.0] - 2025-01-27

### Added
- Initial release
- User authentication with django-allauth
- Client management (CRUD operations)
- Project tracking with status workflow
- Task management with assignments
- Todo lists per task
- Notes system for clients, projects, and tasks
- Salary management with monthly payments
- Team management for admins
- GitHub integration support
- Dashboard with overview metrics
