import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';

/** DynamoDB tables, job queue, and dead-letter queue. Filled in by task 5.2. */
export class DataStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: cdk.StackProps) {
    super(scope, id, props);
  }
}
