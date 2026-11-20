import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';

/** Cognito user pool and app client. Filled in by task 5.1. */
export class AuthStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: cdk.StackProps) {
    super(scope, id, props);
  }
}
