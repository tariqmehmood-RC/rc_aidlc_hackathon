import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';

/** S3 bucket and CloudFront distribution. Filled in by task 5.5. */
export class WebStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: cdk.StackProps) {
    super(scope, id, props);
  }
}
