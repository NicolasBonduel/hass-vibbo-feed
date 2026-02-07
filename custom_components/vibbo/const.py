"""Constants for the Vibbo integration."""

DOMAIN = "vibbo"

CONF_COOKIE = "cookie"
CONF_ORGANIZATION_ID = "organization_id"
CONF_ORGANIZATION_SLUG = "organization_slug"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 30  # minutes
DEFAULT_LIMIT = 10
DEFAULT_API_VERSION = "577"

GRAPHQL_URL = "https://vibbo.no/graphql?name=vibboActivityStream"

GRAPHQL_QUERY = """query vibboActivityStream(
  $organizationId: OrganizationID!
  $limit: Int
  $filter: OrganizationActivityFilter
) {
  stream: activityInOrganization(
    organizationId: $organizationId
    limit: $limit
    filter: $filter
  ) {
    items {
      happenedAt
      item {
        __typename
        ... on News {
          slug
          title
          ingress
          pinned
          topics {
            title
          }
          commentsCount
          thumbsUpCount: reactionCount(type: THUMBS_UP)
        }
        ... on Post {
          slug
          title
          body
          category {
            label
          }
          updatedBy {
            firstName
          }
          commentsCount
          thumbsUpCount: reactionCount(type: THUMBS_UP)
        }
      }
    }
  }
}"""

FRONTEND_SCRIPT_URL = "/vibbo/vibbo-feed-card.js"
