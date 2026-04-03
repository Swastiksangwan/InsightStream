
# Database Notes

## Database
PostgreSQL

## MVP Tables Created
- users
- content
- genres
- content_genres
- platforms
- content_platforms
- ratings
- content_summary
- watched
- watch_later

## Purpose of Important Tables

### users
Stores user account information.

### content
Main table for movies and series.

### genres
Stores genre names.

### content_genres
Links content with genres.

### platforms
Stores OTT platforms and rating sources.

### content_platforms
Links content with OTT availability.

### ratings
Stores ratings from multiple sources and normalized scores.

### content_summary
Stores InsightStream’s final platform summary, unified score, pros, cons, and verdict.

### watched
Stores content marked as watched by a user.

### watch_later
Stores content saved by a user for later viewing.

## Key Relationships
- one content item can have many genres
- one content item can be available on many platforms
- one content item can have many source ratings
- one user can have many watched items
- one user can have many watch-later items

## Product Logic Note
A title should ideally not remain in both watched and watch_later at the same time.
This rule will be handled in backend logic later.
