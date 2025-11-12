@description('Name of the Event Grid Subscription')
param name string

@description('Name of the Event Grid System Topic')
param systemTopicName string

@description('Resource ID of the Azure Function App that will receive blob events')
param functionAppId string

@description('Name of the function within the function app that handles the blob trigger')
param functionName string

@description('Event delivery schema')
@allowed(['EventGridSchema', 'CloudEventSchemaV1_0', 'CustomInputSchema'])
param eventDeliverySchema string = 'EventGridSchema'

@description('Filter for specific blob containers. Leave empty to subscribe to all containers.')
param containerFilters array = []

@description('Filter for blob name prefix patterns')
param subjectBeginsWith string = ''

@description('Filter for blob name suffix patterns (e.g., .pdf, .docx)')
param subjectEndsWith string = ''

@description('Event types to subscribe to')
param includedEventTypes array = [
  'Microsoft.Storage.BlobCreated'
]

@description('Maximum retry attempts for event delivery')
param maxDeliveryAttempts int = 30

@description('Event time to live in minutes')
param eventTimeToLiveInMinutes int = 1440

resource systemTopic 'Microsoft.EventGrid/systemTopics@2024-06-01-preview' existing = {
  name: systemTopicName
}

// Build container filter values if specified
var containerFilterValues = [for container in containerFilters: '/blobServices/default/containers/${container}']

resource eventSubscription 'Microsoft.EventGrid/systemTopics/eventSubscriptions@2024-06-01-preview' = {
  name: name
  parent: systemTopic  // ← Subscribes to the System Topic
  properties: {
    destination: {
      endpointType: 'AzureFunction'
      properties: {
        resourceId: '${functionAppId}/functions/${functionName}'   // ← WHERE to sen
        maxEventsPerBatch: 1
        preferredBatchSizeInKilobytes: 64
      }
    }
    filter: {
      includedEventTypes: includedEventTypes  // ← WHAT events
      subjectBeginsWith: subjectBeginsWith    // ← Path filters
      subjectEndsWith: subjectEndsWith        // ← File extension filters
      enableAdvancedFilteringOnArrays: true
      advancedFilters: empty(containerFilters) ? [] : [  // ← Container filters
        {
          operatorType: 'StringContains'
          key: 'subject'
          values: containerFilterValues
        }
      ]
    }
    eventDeliverySchema: eventDeliverySchema
    retryPolicy: {
      maxDeliveryAttempts: maxDeliveryAttempts    // ← Retry logic
      eventTimeToLiveInMinutes: eventTimeToLiveInMinutes
    }
  }
}

@description('The resource ID of the Event Grid Subscription')
output id string = eventSubscription.id

@description('The name of the Event Grid Subscription')
output name string = eventSubscription.name
