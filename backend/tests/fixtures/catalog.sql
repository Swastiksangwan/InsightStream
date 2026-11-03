-- Synthetic, deterministic enrichment for the canonical 15-title test seed.
-- Never run this file against development. It is loaded by guarded test tools.

-- These registries are normally seeded by schema.sql. Per-case DATA resets
-- deliberately do not execute schema DDL, so seed the registries explicitly.
INSERT INTO rating_sources(source_name,display_name,source_category,
    raw_score_scale_default,weight,is_active,source_url)
VALUES
 ('tmdb','TMDb','audience',10,1,TRUE,'https://www.themoviedb.org/'),
 ('imdb','IMDb','audience',10,1,TRUE,'https://developer.imdb.com/non-commercial-datasets/'),
 ('letterboxd','Letterboxd','audience',5,0,TRUE,'https://letterboxd.com/');
INSERT INTO keyword_sources(source_name,display_name,is_active)
VALUES ('tmdb','TMDb',TRUE);

UPDATE content SET original_title=title, original_language='en';

INSERT INTO content (tmdb_id,title,original_title,content_type,overview,poster_url,
    backdrop_url,release_date,latest_activity_date,year,runtime,language,
    original_language,status,age_rating)
VALUES
 (872585,'Oppenheimer','Oppenheimer','movie','Synthetic certification fixture.',
  'https://example.invalid/poster.jpg','https://example.invalid/backdrop.jpg',
  '2023-07-21','2023-07-21',2023,180,'English','en','Released','R'),
 (900000001,'US Availability Fixture','US Availability Fixture','movie',
  'Synthetic US fallback fixture.','https://example.invalid/poster.jpg',
  'https://example.invalid/backdrop.jpg','2000-01-01','2000-01-01',2000,90,
  'English','en','Released','R'),
 (900000002,'No Availability Fixture','No Availability Fixture','movie',
  'Synthetic missing-data fixture.','https://example.invalid/poster.jpg',
  'https://example.invalid/backdrop.jpg','2000-01-01','2000-01-01',2000,90,
  'English','en','Released',NULL);

UPDATE content SET poster_url=NULL,backdrop_url=NULL
WHERE title IN ('US Availability Fixture','No Availability Fixture');

INSERT INTO external_ids(content_id,source_name,external_id)
SELECT id,'tmdb',tmdb_id::text FROM content
WHERE title IN ('Oppenheimer','US Availability Fixture','No Availability Fixture');
INSERT INTO external_ids(content_id,source_name,external_id)
SELECT id,'imdb','tt'||lpad(id::text,7,'0') FROM content
WHERE title IN ('Oppenheimer','US Availability Fixture','No Availability Fixture');
INSERT INTO content_genres(content_id,genre_id)
SELECT c.id,g.id FROM content c CROSS JOIN genres g
WHERE c.title IN ('Oppenheimer','US Availability Fixture','No Availability Fixture')
AND g.name='Drama';

-- Equal scores with different scoring-source counts exercise the former tie skip.
-- Barbie and the two synthetic fallback titles intentionally have no rating rows.
INSERT INTO content_ratings(content_id,rating_source_id,raw_score,raw_score_scale,
    normalized_score,vote_count,rating_count_label,fetched_at)
SELECT c.id,s.id,8,10,80,1000,'1,000 fixture votes','2026-07-10'
FROM content c CROSS JOIN rating_sources s
WHERE s.source_name='tmdb'
AND c.title NOT IN ('Barbie','US Availability Fixture','No Availability Fixture');
INSERT INTO content_ratings(content_id,rating_source_id,raw_score,raw_score_scale,
    normalized_score,vote_count,rating_count_label,rating_url,fetched_at)
SELECT c.id,s.id,8,10,80,2000,'2,000 fixture votes',
    'https://www.imdb.com/title/tt0816692/','2026-07-10'
FROM content c CROSS JOIN rating_sources s
WHERE c.title='Interstellar' AND s.source_name='imdb';

INSERT INTO platforms(name,platform_type) VALUES ('JioHotstar','ott');
INSERT INTO content_availability(content_id,platform_id,availability_type,
    region_code,source_name,source_provider_id,display_priority,fetched_at)
SELECT c.id,p.id,'streaming','IN','tmdb','fixture-provider',1,'2026-07-10'
FROM content c CROSS JOIN platforms p
WHERE (c.title='Oppenheimer' AND p.name='JioHotstar')
OR (c.title IN ('Interstellar','The Mandalorian') AND p.name='Netflix');
INSERT INTO content_availability(content_id,platform_id,availability_type,
    region_code,source_name,source_provider_id,display_priority,fetched_at)
SELECT c.id,p.id,'buy','US','tmdb','fixture-provider',1,'2026-07-10'
FROM content c CROSS JOIN platforms p
WHERE c.title='US Availability Fixture' AND p.name='Prime Video';
INSERT INTO content_certifications(content_id,certification,country_code,
    rating_system,source_name,source_priority,fetched_at)
SELECT id,'UA','IN','CBFC','tmdb',1,'2026-07-10' FROM content WHERE title='Oppenheimer';
INSERT INTO content_certifications(content_id,certification,country_code,
    rating_system,source_name,source_priority,fetched_at)
SELECT id,'PG-13','US','MPAA','tmdb',1,'2026-07-10' FROM content WHERE title='US Availability Fixture';

INSERT INTO people(name,known_for_department,biography,birthday,place_of_birth)
VALUES
 ('Christopher Nolan','Directing','Synthetic test biography.','1970-07-30','Fixture location'),
 ('Matthew McConaughey','Acting','Synthetic test biography.',NULL,NULL),
 ('Jon Favreau','Directing','Synthetic test biography.',NULL,NULL),
 ('Pedro Pascal','Acting','Synthetic test biography.',NULL,NULL);
INSERT INTO person_external_ids(person_id,source_name,external_id)
SELECT id,'tmdb',(900000000+id)::text FROM people;
INSERT INTO content_people(content_id,person_id,role_type,character_name,job,
    department,display_order,source_name,source_credit_id)
SELECT c.id,p.id,'cast','Cooper',NULL,'Acting',0,'fixture','fixture-cooper'
FROM content c CROSS JOIN people p
WHERE c.title='Interstellar' AND p.name='Matthew McConaughey';
INSERT INTO content_people(content_id,person_id,role_type,job,department,source_name,source_credit_id)
SELECT c.id,p.id,r.role_type,r.job,'Directing','fixture','fixture-nolan-'||r.role_type
FROM content c CROSS JOIN people p CROSS JOIN
 (VALUES ('director','Director'),('crew','Writer')) r(role_type,job)
WHERE c.title='Interstellar' AND p.name='Christopher Nolan';
INSERT INTO content_people(content_id,person_id,role_type,character_name,department,
    display_order,source_name,source_credit_id)
SELECT c.id,p.id,'cast','Din Djarin','Acting',0,'fixture','fixture-mandalorian-cast'
FROM content c CROSS JOIN people p
WHERE c.title='The Mandalorian' AND p.name='Pedro Pascal';
INSERT INTO content_people(content_id,person_id,role_type,job,department,source_name,source_credit_id)
SELECT c.id,p.id,r.role_type,r.job,'Writing','fixture','fixture-favreau-'||r.role_type
FROM content c CROSS JOIN people p CROSS JOIN
 (VALUES ('creator','Creator'),('crew','Writer')) r(role_type,job)
WHERE c.title='The Mandalorian' AND p.name='Jon Favreau';

INSERT INTO content_series_metadata(content_id,number_of_seasons,number_of_episodes,
    series_status,series_status_normalized,in_production,first_air_date,last_air_date,
    last_episode_air_date,series_type,released_seasons_count,announced_seasons_count,
    has_announced_season,source_name,last_refreshed_at)
SELECT id,3,24,'Ended','ended',FALSE,release_date,'2026-07-09','2026-07-09',
    'Scripted',3,0,FALSE,'fixture','2026-07-10' FROM content WHERE content_type='series';
UPDATE content SET latest_activity_date='2026-07-09' WHERE content_type='series';

INSERT INTO source_signal_import_runs(run_key,db_write_performed,dry_run,titles_seen,titles_imported)
VALUES ('pytest-fixture-v1',TRUE,FALSE,16,16);
INSERT INTO content_watch_guidance(content_id,last_signal_run_id,watch_feel,chips,
    best_for,consider_first,signal_sources,storage_ready,frontend_ready)
SELECT c.id,r.id,'Synthetic fixture guidance.','["Sci-fi","Thoughtful"]'::jsonb,
    '["Thoughtful stories"]'::jsonb,'[]'::jsonb,'["fixture"]'::jsonb,TRUE,FALSE
FROM content c CROSS JOIN source_signal_import_runs r
WHERE c.title NOT IN ('US Availability Fixture','No Availability Fixture');
INSERT INTO content_source_signals(content_id,last_signal_run_id,dimension,value,label,
    confidence,source_names,source_payload)
SELECT c.id,r.id,v.dimension,v.value,v.label,'medium','["fixture"]'::jsonb,
    '{"spoiler_safe":true}'::jsonb
FROM content c CROSS JOIN source_signal_import_runs r CROSS JOIN
 (VALUES ('topic_theme','space exploration','Space exploration'),
         ('mood','thoughtful','Thoughtful')) v(dimension,value,label)
WHERE c.title NOT IN ('US Availability Fixture','No Availability Fixture');
INSERT INTO content_source_signals(content_id,last_signal_run_id,dimension,value,label,
    confidence,source_names,source_payload)
SELECT c.id,r.id,v.dimension,v.value,v.label,'medium','["fixture"]'::jsonb,
    '{"spoiler_safe":true}'::jsonb
FROM content c CROSS JOIN source_signal_import_runs r CROSS JOIN
 (VALUES ('Interstellar','pacing','slow-burn','Slow-burn'),
         ('Inception','pacing','fast-paced','Fast-paced'),
         ('Dark','tone','dark','Dark'),
         ('The Mandalorian','tone','light','Light')) v(title,dimension,value,label)
WHERE c.title=v.title;

INSERT INTO provider_keywords(source_id,external_keyword_id,keyword_name,normalized_keyword_name)
SELECT id,'900000001','space exploration','space exploration' FROM keyword_sources WHERE source_name='tmdb';
INSERT INTO content_keywords(content_id,keyword_id,source_id,confidence)
SELECT c.id,k.id,k.source_id,'medium' FROM content c CROSS JOIN provider_keywords k
WHERE c.title='Interstellar';
