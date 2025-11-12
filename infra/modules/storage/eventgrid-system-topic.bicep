@description('Name of the Event Grid System Topic')
param name string

@description('Location for the Event Grid System Topic')
param location string = resourceGroup().location

@description('Tags for the resource')
param tags object = {}

@description('Resource ID of the source storage account')
param storageAccountId string

@description('Topic type - for blob events use Microsoft.Storage.StorageAccounts')
param topicType string = 'Microsoft.Storage.StorageAccounts'

@description('Identity type for the system topic')
param identityType string = 'None'

resource systemTopic 'Microsoft.EventGrid/systemTopics@2024-06-01-preview' = {
  name: name
  location: location
  tags: tags
  identity: {
    type: identityType
  }
  properties: {
    source: storageAccountId  // ← The storage account to monitor
    topicType: topicType      // ← Type: Microsoft.Storage.StorageAccounts
  }
}

@description('The resource ID of the Event Grid System Topic')
output id string = systemTopic.id

@description('The name of the Event Grid System Topic')
output name string = systemTopic.name

@description('The endpoint URL of the Event Grid System Topic')
output endpoint string = systemTopic.properties.metricResourceId
