# Clinect - Clinical Trial Patient Matching Platform

## Project Overview
Clinect is a platform designed to connect patients with relevant clinical trials by leveraging the ClinicalTrials.gov API and advanced data processing technologies.

## Core Technologies

### Data Source
- **ClinicalTrials.gov Data API**: https://clinicaltrials.gov/data-api/api
  - Primary data source for clinical trial information
  - Provides comprehensive trial metadata, eligibility criteria, locations, and status

### Technology Stack
- **PySpark**: Large-scale data processing and ETL pipelines
- **PostgreSQL**: Relational database for structured clinical trial data
  - **psycopg**: PostgreSQL adapter for Python
- **MongoDB**: Document store for flexible trial metadata and patient profiles
- **Neo4j**: Graph database for relationship mapping between patients, trials, conditions, and treatments
- **Flask**: Lightweight Python web framework for backend API

## Architecture Concept

### Data Pipeline
1. **Ingestion**: Fetch clinical trial data from ClinicalTrials.gov API
2. **Processing**: Use PySpark to clean, transform, and enrich trial data
3. **Storage**:
   - PostgreSQL: Core trial information, patient records
   - MongoDB: Flexible trial documents, search indices
   - Neo4j: Relationship graphs (conditions � trials, locations � trials, etc.)

### Key Features (Planned)
- Patient profile creation with medical history
- Intelligent trial matching based on eligibility criteria
- Location-based trial search
- Trial status tracking and notifications
- Multi-dimensional filtering (condition, phase, location, etc.)

## Data Model Ideas

### PostgreSQL
- Structured trial metadata
- Patient demographic and medical data
- Trial enrollment tracking

### MongoDB
- Full trial documents from API
- Complex eligibility criteria
- Patient medical history documents

### Neo4j
- Patient-Condition-Trial relationships
- Condition hierarchies
- Geographic proximity mapping
- Treatment pathways

## Development Notes
- Start with API exploration and data schema design
- Build incremental data pipeline
- Focus on matching algorithm development
- Consider real-time vs batch processing needs

## Package Management
- This project uses **uv** for Python package management
- Always use `uv run <script>` to run Python scripts (e.g., `uv run app.py`, `uv run init_db.py`)
- uv automatically manages the virtual environment - no need to manually activate it
- Use `uv sync` to install/update dependencies
- Use `uv add <package>` to add new dependencies

## Running the Project
See [README.md](README.md) for complete setup instructions.

## Important Instruction Reminders
Do what has been asked; nothing more, nothing less.
NEVER create files unless they're absolutely necessary for achieving your goal.
ALWAYS prefer editing an existing file to creating a new one.
NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the User.
