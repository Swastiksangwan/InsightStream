New reviewed transactional migrations belong here: `016_description.sql`, then
`017_description.sql`, without gaps. Historical SQL in the parent directory is
archived evidence and is never discovered as pending work.

Each file starts with `-- insightstream-migration: transactional`. See
[Database Setup and Recovery](../../../docs/backend_database_setup.md) for supported
SQL, baseline profiles, preview, disposable testing and approved application.
