"""Read-only PostgreSQL 18 schema signatures; no application rows or owners."""

from scripts.database_snapshot import canonical_constraint, digest


MANAGEMENT_SCHEMA = "insightstream_migrations"


def schema_description(connection, namespace="public"):
    """Keep names, types, defaults, validity, sequence definitions and SQL shape.

    Owners and sequence *values* vary between installations/data imports. They
    are deliberately excluded; database identity/privileges are checked separately.
    PostgreSQL deparser output is version-specific, so only major 18 is supported.
    """
    queries = {
        "columns": """SELECT c.relname,a.attnum,a.attname,
            format_type(a.atttypid,a.atttypmod),a.attnotnull,a.attidentity,a.attgenerated,
            pg_get_expr(d.adbin,d.adrelid),coll.collname
            FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
            LEFT JOIN pg_collation coll ON coll.oid=a.attcollation
            WHERE n.nspname=%s AND a.attnum>0 AND NOT a.attisdropped
            ORDER BY c.relname,a.attnum""",
        "constraints": """SELECT c.relname,x.conname,x.contype,
            pg_get_constraintdef(x.oid),x.convalidated,x.condeferrable,x.condeferred
            FROM pg_constraint x JOIN pg_class c ON c.oid=x.conrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s
            ORDER BY c.relname,x.conname""",
        "indexes": """SELECT c.relname,pg_get_indexdef(c.oid),i.indisvalid,i.indisready,
            i.indisreplident FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s
            ORDER BY c.relname""",
        "relations": """SELECT c.relname,c.relkind,c.relpersistence,c.relrowsecurity,
            c.relforcerowsecurity,c.reloptions,pg_get_expr(c.relpartbound,c.oid),
            COALESCE(t.spcname,'pg_default')
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            LEFT JOIN pg_tablespace t ON t.oid=c.reltablespace
            WHERE n.nspname=%s ORDER BY c.relname""",
        "sequences": """SELECT c.relname,format_type(s.seqtypid,NULL),s.seqstart,
            s.seqincrement,s.seqmax,s.seqmin,s.seqcache,s.seqcycle,
            owned.relname,a.attname
            FROM pg_sequence s JOIN pg_class c ON c.oid=s.seqrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            LEFT JOIN pg_depend d ON d.objid=c.oid AND d.classid='pg_class'::regclass
                AND d.deptype IN ('a','i')
            LEFT JOIN pg_class owned ON owned.oid=d.refobjid
            LEFT JOIN pg_attribute a ON a.attrelid=d.refobjid AND a.attnum=d.refobjsubid
            WHERE n.nspname=%s ORDER BY c.relname""",
        "routines": """SELECT p.proname,pg_get_function_identity_arguments(p.oid),
            pg_get_functiondef(p.oid) FROM pg_proc p
            JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=%s
            ORDER BY 1,2""",
        "triggers": """SELECT c.relname,t.tgname,pg_get_triggerdef(t.oid),t.tgenabled
            FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname=%s AND NOT t.tgisinternal ORDER BY 1,2""",
        "views": """SELECT c.relname,pg_get_viewdef(c.oid)
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname=%s AND c.relkind IN ('v','m') ORDER BY 1""",
        "types": """SELECT t.typname,t.typtype,t.typnotnull,t.typdefault,
            e.enumlabel,e.enumsortorder FROM pg_type t
            JOIN pg_namespace n ON n.oid=t.typnamespace
            LEFT JOIN pg_enum e ON e.enumtypid=t.oid
            WHERE n.nspname=%s ORDER BY 1,e.enumsortorder""",
        "policies": """SELECT c.relname,p.polname,p.polcmd,p.polpermissive,
            pg_get_expr(p.polqual,p.polrelid),pg_get_expr(p.polwithcheck,p.polrelid)
            FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s
            ORDER BY 1,2""",
        "rules": """SELECT c.relname,r.rulename,pg_get_ruledef(r.oid)
            FROM pg_rewrite r JOIN pg_class c ON c.oid=r.ev_class
            JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s
            ORDER BY 1,2""",
        "collations": """SELECT collname,collprovider,collisdeterministic,collencoding,
            collcollate,collctype,collversion FROM pg_collation c
            JOIN pg_namespace n ON n.oid=c.collnamespace WHERE n.nspname=%s ORDER BY 1""",
    }
    result = {}
    with connection.cursor() as cursor:
        for name, query in queries.items():
            cursor.execute(query, (namespace,))
            result[name] = [list(row) for row in cursor.fetchall()]
    for row in result["constraints"]:
        row[3] = canonical_constraint(row[3])
    return result


def schema_signature(connection, namespace="public"):
    return digest(schema_description(connection, namespace))


def environment_shape(connection):
    with connection.cursor() as cursor:
        cursor.execute("""SELECT nspname FROM pg_namespace
            WHERE nspname !~ '^pg_' AND nspname<>'information_schema'
            AND nspname<>%s ORDER BY 1""", (MANAGEMENT_SCHEMA,))
        namespaces = [row[0] for row in cursor.fetchall()]
        cursor.execute("""SELECT e.extname,e.extversion,n.nspname FROM pg_extension e
            JOIN pg_namespace n ON n.oid=e.extnamespace ORDER BY 1""")
        extensions = [list(row) for row in cursor.fetchall()]
        cursor.execute("""SELECT pg_encoding_to_char(encoding),datcollate,datctype,datlocprovider
            FROM pg_database WHERE datname=current_database()""")
        locale = list(cursor.fetchone())
    return {"namespaces": namespaces, "extensions": extensions, "database_locale": locale}
