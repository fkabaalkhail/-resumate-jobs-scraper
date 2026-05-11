# Entry-Level Tech Jobs Aggregator

A job aggregation pipeline that scrapes entry-level tech positions (internships and new grad roles) from major ATS platforms across 200+ companies in the US and Canada.

## What This Does

- Scrapes job listings from Greenhouse, Lever, Ashby, and Workday career boards
- Filters for entry-level positions (intern, new grad, junior, associate)
- Covers 200+ top tech companies
- Updates hourly via GitHub Actions
- US and Canada positions only

## Categories

Software Engineering, Data Analysis, Machine Learning/AI, Product Management, Marketing, Design, Business Analyst, Accounting/Finance, Sales, Human Resources, DevOps/Infrastructure, Cybersecurity, and more.

## Schedule

Runs every hour via GitHub Actions cron. Each run scrapes all configured company boards and stores new listings.
