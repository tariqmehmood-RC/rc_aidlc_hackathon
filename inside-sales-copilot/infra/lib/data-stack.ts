import * as cdk from 'aws-cdk-lib';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as sqs from 'aws-cdk-lib/aws-sqs';
import { Construct } from 'constructs';

/**
 * Tables and the job queue (task 5.2). Shapes match backend/src/lib/brief_store.py,
 * backend/src/services/rules.py and research.py.
 */
export class DataStack extends cdk.Stack {
  readonly briefs: dynamodb.Table;
  readonly rules: dynamodb.Table;
  readonly researchCache: dynamodb.Table;
  readonly jobs: sqs.Queue;
  readonly deadLetters: sqs.Queue;

  constructor(scope: Construct, id: string, props: cdk.StackProps) {
    super(scope, id, props);
    const common = {
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      encryption: dynamodb.TableEncryption.AWS_MANAGED,
      removalPolicy: cdk.RemovalPolicy.DESTROY, // hackathon data only, briefs expire after 30 days anyway
    };

    this.briefs = new dynamodb.Table(this, 'Briefs', {
      ...common,
      partitionKey: { name: 'briefId', type: dynamodb.AttributeType.STRING },
      timeToLiveAttribute: 'expiresAt', // 30 days after creation (R8.7)
    });
    this.briefs.addGlobalSecondaryIndex({
      indexName: 'byUser',
      partitionKey: { name: 'userId', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'createdAt', type: dynamodb.AttributeType.NUMBER },
      projectionType: dynamodb.ProjectionType.ALL,
    });
    this.briefs.addGlobalSecondaryIndex({
      indexName: 'byQueue', // sparse: only queued briefs have queueKey
      partitionKey: { name: 'queueKey', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'queuedAt', type: dynamodb.AttributeType.NUMBER },
      projectionType: dynamodb.ProjectionType.KEYS_ONLY,
    });

    this.rules = new dynamodb.Table(this, 'Rules', {
      ...common,
      partitionKey: { name: 'userId', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'ruleId', type: dynamodb.AttributeType.STRING },
    });

    this.researchCache = new dynamodb.Table(this, 'ResearchCache', {
      ...common,
      partitionKey: { name: 'companyDomain', type: dynamodb.AttributeType.STRING },
      timeToLiveAttribute: 'expiresAt', // 7 days (R3.11)
    });

    this.deadLetters = new sqs.Queue(this, 'JobsDeadLetters', {
      retentionPeriod: cdk.Duration.days(14),
      encryption: sqs.QueueEncryption.SQS_MANAGED,
      enforceSSL: true,
    });
    this.jobs = new sqs.Queue(this, 'Jobs', {
      visibilityTimeout: cdk.Duration.seconds(1080), // 6 x the worker's 180 s timeout
      retentionPeriod: cdk.Duration.days(1),
      encryption: sqs.QueueEncryption.SQS_MANAGED,
      enforceSSL: true,
      deadLetterQueue: { queue: this.deadLetters, maxReceiveCount: 3 },
    });
  }
}
