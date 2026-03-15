<div align="center">
  <h1>StartupScout 🔍</h1>
</div>

StartupScout is a powerful but easy-to-use web scraper designed to collect data about startups. It visits popular startup directories, extracts details about the companies, cleans up that information, and saves it into simple CSV and JSON files for you to use.

## What Websites Does It Scrape?

The tool is capable of pulling startup profiles from 7 different public registries:

1. **Y Combinator** - The famous startup accelerator. We pull right from their public directory index.
2. **Product Hunt** - Specifically targeted to capture new tech product launches and the companies behind them.
3. **BetaList** - A platform where early-stage startups list their coming-soon products. 
4. **Wellfound (formerly AngelList)** - One of the largest hubs for startup job listings and company profiles.
5. **F6S** - A massive community directory for founders and startup programs.
6. **SaaSHub** - A software discovery platform focused on B2B SaaS (Software as a Service) startups.
7. **Launching Next** - A directory that features brand new startup companies every day.

## How Does It Better The Data?

Raw data from the internet is often messy. StartupScout automatically cleans and improves this data before saving it:

- **Automatic Deduplication:** Often, a startup might be listed on both Product Hunt and BetaList. StartupScout automatically detects this and merges the records so you don't get duplicates in your final CSV.
- **Smart Data Cleaning:** It fixes broken URLs, standardizes city/country names, and removes messy HTML tags from descriptions.
- **AI Enrichment (Optional):** If you connect a Groq API key, the tool asks an AI to read every startup's description and automatically assign it an industry (like "SaaS" or "Fintech") and write a clean 1-sentence summary of what the company does.

## Setup Instructions

To get started, you'll need Python 3.11 or higher installed on your computer.

```bash
# 1. Clone the repository
git clone https://github.com/Eren-Sama/StartupScout.git
cd StartupScout

# 2. Install the required Python packages
pip install -e .

# 3. Install Playwright (the bot that browses the websites)
playwright install chromium

# 4. Copy the environment variables file
cp .env.example .env
```

### Getting Your API Keys

- **Groq API Key (Optional):** Used for AI enrichment. Get it for free at [console.groq.com](https://console.groq.com).
- **YC Algolia API Key (Required for YC Scraper):** Y Combinator uses a public Algolia search key on their website. To find it:
  1. Go to [ycombinator.com/companies](https://www.ycombinator.com/companies)
  2. Open your browser's Developer Tools (F12) -> **Network** tab
  3. Search for a company, and look for a network request to `algolia.net`
  4. Look at the **Headers** of that request. You will see `x-algolia-api-key` and `x-algolia-application-id`. Copy those into your `.env` file!

## How to Use It

StartupScout is built to be simple to use. Just run this command to start the interactive menu:

```bash
python -m src.main
```

The app will prompt you with simple questions:
* Which of the 7 websites do you want to scrape? (You can choose one, multiple, or all)
* How many companies do you want to grab from each? 
* Do you want the final data as a `.csv` file, a `.json` file, or both?
* What folder do you want to save the data in?
* Do you want the AI to read the descriptions and classify the startups?

Answer the prompts, and the scraper will do the rest automatically!

## Output Files

Once the scraper finishes, it will save three files in your chosen folder:
- `startups.csv` (The clean data, perfect for opening in Excel or Google Sheets)
- `startups.json` (The same data, but formatted for developers/databases)
- `quality_report.json` (A small report telling you if any listings were missing data like website links)

## License

MIT License
