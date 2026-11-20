import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';

/** HTTP API, API Lambdas, worker Lambda, alarms. Filled in by task 5.4. */
export class ApiStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: cdk.StackProps) {
    super(scope, id, props);
  }
}
