# Job application and contacts manager

## Problem and approach

Build a containerized Python web application for organizing job opportunities, application progress, job-related PDFs, company contacts, interaction history, and follow-up reporting. Provide a kanban-like board with jobs grouped by their current application status. Start with manually entered job links; keep the design cloud-migration friendly without adding job-site scraping to the first release.

Use Django for its integrated data modeling, forms, authentication foundation, and admin; PostgreSQL for relational data; and server-rendered pages for a focused CRUD-oriented first release. Package the application with Docker and provide a local persistent volume for uploaded PDFs behind a storage abstraction so object storage can be introduced later.

## Scope decisions

- Initial release is single-user/private deployment. Do not build multi-tenant account management.
- Add and edit job postings manually. Defer automated job-site discovery.
- Store PDFs on persistent local storage through a replaceable storage interface.
- Track the current application stage and preserve stage-change history.
- Provide a kanban-like jobs board with a column for each current application stage and job cards showing key details.
- Model companies, jobs, contacts, and interactions so each job can have zero or more contacts; allow contacts to be associated with multiple jobs at the same company.
- Support job/application documents such as resumes and submitted application files.
- Report application counts grouped by current status for applications applied within a selected date range.
- Show contacts with no recorded interaction during the previous six months, including contacts never contacted.

## Todos

1. Establish the Django project, containerized development setup, and PostgreSQL configuration.
2. Implement the company, job/application, contact, stage-history, interaction, and document data model with relationships and migrations.
3. Implement usable web pages and forms to manage jobs, company details, contacts, stages, interactions, and related links; include a kanban-like board grouping jobs by current stage.
4. Implement PDF upload, listing, download, and deletion with persistent local storage and basic file validation.
5. Add reports for applications applied within a selected date range, grouped by current status, and contacts with no interaction in the prior six months.
6. Add focused tests and setup/usage documentation; verify the containerized app and core workflows.

## Notes and considerations

- Keep application configuration externalized for future cloud deployment; do not bind the design to a particular cloud provider.
- Use a controlled stage vocabulary including job found, applied, denied, HR interview, and other interview stages; preserve historical transitions rather than only overwriting the current stage.
- Store interaction date, type (email, phone, interview, or other), notes, contact, and optional related job.
- Base the application report's date filter on the applied date and group by each application's current status at report time.
- Define "not contacted in six months" as having no recorded interaction in the rolling six months before the report is viewed; include contacts with no interaction history.
- Store document metadata in the relational database and file bytes in the configured storage backend.
- No implementation is included in this planning step.
