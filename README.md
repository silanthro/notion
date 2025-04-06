# silanthro/notion

Tools for interacting with Notion pages.

This requires the following environment variables:

- `NOTION_INTEGRATION_SECRET`: Your Notion Integration secret.

## Retrieve the Notion Integration secret

Create an Integration by following the instructions at https://www.notion.so/profile/integrations/.

Then, if this is an Internal Integration, you need to grant access to specific pages with the following steps:

1. Go to the page you want to grant access to
2. Click on the three dots at the top right corner, click on "Connections" (usually the last item in the menu), and search for your Integration
3. Click on your Integration to enable access to this page and its children
