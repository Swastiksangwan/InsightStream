# InsightStream Product Direction and MVP Boundary

## 1. Current Product Positioning

InsightStream is an information-first entertainment decision-support platform for movies and series.

The product should organize content data, ratings, summaries, availability, and personal watch activity so users can make faster and clearer viewing decisions. Its purpose is to reduce scattered browsing and help users understand whether a title is worth their time.

The current product direction is closer to:

- IMDb-style structured information
- JustWatch-style availability awareness
- Rotten Tomatoes/Metacritic-style rating comparison
- an InsightStream-specific analytics and decision-support layer

InsightStream is not currently trying to be:

- Reddit
- Instagram
- Discord
- Letterboxd-style public social reviewing
- a full fandom community platform

## 2. What the MVP Should Help Users Do

The MVP should help users answer practical viewing-decision questions:

- What is trending right now?
- What is popular or highly rated?
- What is this movie or series about?
- Where can I watch it?
- How is it rated across platforms?
- What do critics and audiences generally think?
- What are the pros, cons, and verdict?
- Should I watch it?
- What have I already watched?
- What do I want to watch later?

## 3. MVP Features Included

The following features belong in the MVP:

- Content browsing: users should be able to browse movies and series in a structured way.
- Content detail pages: each title should have organized information, ratings, summaries, and availability.
- Trending/top-rated/recent discovery sections: users should be able to discover relevant titles through curated data-driven sections.
- Search and filtering: users should be able to find titles quickly.
- Genre/platform/content-type filters: users should be able to narrow browsing by practical viewing criteria.
- Cross-platform ratings: users should see rating data from multiple sources in one place.
- Critic/audience/general rating breakdown: ratings should be grouped in a way that helps users understand different perspectives.
- Review summaries: the platform should simplify broad review signals into readable insights.
- Pros/cons/verdict: each title can include concise decision-support text.
- Platform availability: users should understand where content is available and how it can be watched.
- Watch later: users should be able to save titles for future viewing.
- Watched: users should be able to track completed titles.
- Basic recommendation logic later: recommendations can be added after the current data and API foundation is stable.
- Data collection and analytics foundation: the project should continue building toward richer data ingestion, scoring, and analysis.

Current implementation note: the frontend MVP loop now supports browsing, discovery, detail viewing, reversible personal watch actions, and Watch Later/Watched pages using temporary demo user state. Frontend polish pass 1 has also been completed. This remains personal utility behavior, not public or social behavior.

Future detail-page improvements should focus on stronger analytics, real poster/backdrop data, richer labels, director/cast/crew/person support, clickable genre navigation, and clickable director/cast/crew/person entries after backend schema/API expansion. The frontend should not fake this richer metadata before backend support exists.

## 4. MVP Features Excluded For Now

The following features are excluded from the current MVP:

- Public user reviews
- User posts
- Comments
- Public profiles
- Social feeds
- Likes/followers
- Communities
- Polls
- Memes/edits
- Fan theories
- Discussion threads
- Moderation systems

These features are intentionally excluded to avoid scope creep and keep the project focused on structured information, analytics, and decision support. Public social and community features would add product complexity, moderation needs, user identity concerns, and a very different engagement model.

## 5. Difference Between Displaying Reviews and Allowing Reviews

There is an important distinction between displaying review-derived information and allowing users to publish reviews.

Allowed in the MVP:

- Showing external ratings
- Showing source-wise rating data
- Showing summarized review insights
- Showing critic/audience/general sentiment
- Showing pros, cons, and verdict generated or stored by the platform

Not allowed in the MVP:

- Users submitting public reviews
- Users posting opinions publicly
- Users commenting or discussing publicly
- Community-based review feeds

InsightStream can summarize and organize review signals without becoming a public review platform.

## 6. User Interaction Boundary

User interaction in the MVP should remain personal and utility-focused.

Allowed:

- Watch later
- Watched
- Maybe favorites later
- Maybe private ratings later
- Maybe private notes later
- Maybe custom collections later

Not included now:

- Public posting
- Public reviews
- Public comments
- Community participation

The interaction model should help users manage their own viewing decisions, not publish content to other users.

## 7. Data Analytics Importance

Data analytics remains a core part of InsightStream.

The platform should eventually include:

- Data collection
- Metadata ingestion
- Rating normalization
- Unified score calculation
- Review/sentiment summarization
- Trending/popularity logic
- Recommendation logic
- Cleaned datasets and analytics scripts

This analytics layer is what separates InsightStream from a simple CRUD app. The long-term value comes from collecting, cleaning, comparing, and interpreting entertainment data in a way that supports better decisions.

## 8. Future Expansion Possibilities

Public reviews, posts, communities, and broader VibeVerse-style features are future expansion layers only.

Possible later phases include:

- Authentication
- Private user ratings
- Private notes
- Favorites
- Custom collections
- Optional public reviews
- Person/celebrity pages
- Community system
- Universal entertainment expansion beyond movies/series

These should only be considered after the core film/series MVP, analytics foundation, and frontend are stable.

## 9. Relation to VibeVerse

VibeVerse remains a possible long-term expansion vision, but it is not the current MVP. InsightStream should first become a strong film/series decision-support product before expanding into public reviews, communities, universal entity types, or broader fandom features.

Current priority:

- Film/series information
- Ratings and summaries
- Discovery
- Availability
- Analytics
- Personal watch actions

Future VibeVerse-style features should only be considered after the core MVP, analytics foundation, and frontend are stable.

## 10. Final Decision

InsightStream MVP will remain an information-first entertainment decision-support platform. It will focus on organized content information, cross-platform ratings, review summaries, discovery, availability, analytics, and personal watch actions. Public user reviews, posts, and communities are not part of the MVP and may only be reconsidered in a later expansion phase.
