import * as cdk from 'aws-cdk-lib';
import { ApiStack } from './api-stack';
import { AuthStack } from './auth-stack';
import { DataStack } from './data-stack';
import { WebStack } from './web-stack';

/** The only region this project uses. It is never read from the shell or from context. */
export const REGION = 'us-east-1';

export function createApp(): cdk.App {
  const app = new cdk.App();
  const env: cdk.Environment = { account: process.env.CDK_DEFAULT_ACCOUNT, region: REGION };

  new AuthStack(app, 'AuthStack', { env });
  new DataStack(app, 'DataStack', { env });
  new ApiStack(app, 'ApiStack', { env });
  new WebStack(app, 'WebStack', { env });
  return app;
}
