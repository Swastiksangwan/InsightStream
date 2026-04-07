# Database Notes

## Database
PostgreSQL

---

## MVP Tables

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

---

## Table Descriptions

### users
Stores user account information.

### content
Primary table containing movies and series data.

### genres
Stores genre categories.

### content_genres
Maps content items to their respective genres.

### platforms
Stores OTT platforms and rating sources.

### content_platforms
Maps content availability across platforms.

### ratings
Stores ratings from multiple sources along with normalized scores.

### content_summary
Stores InsightStream’s aggregated insights including:
- unified score  
- pros  
- cons  
- final verdict  

### watched
Tracks content marked as watched by users.

### watch_later
Tracks content saved for future viewing.

---

## Relationships

- One content item can have multiple genres  
- One content item can be available on multiple platforms  
- One content item can have multiple ratings  
- One user can have multiple watched items  
- One user can have multiple watch-later items  

---

## Business Logic Note

A content item should not exist in both **watched** and **watch_later** simultaneously.  
This constraint will be enforced at the backend level.

---

## Current Status

- Database schema designed and implemented  
- Sample data inserted and tested  
- Backend structure connected with PostgreSQL  
- Content API initialized for data access  