import * as cdk from 'aws-cdk-lib';
import * as cognito from 'aws-cdk-lib/aws-cognito';
import { Construct } from 'constructs';

/**
 * Cognito user pool and the web app client (task 5.1, requirement R1).
 * - No self sign-up: an administrator creates users (scripts/seed-demo-users).
 * - Sign-in with email and password through SRP (aws-amplify).
 * - custom:bu holds the business unit. The app client can read it but cannot write it,
 *   so a user cannot move themselves to another BU (R1.10).
 * - ID and access tokens are valid for 1 hour (R1.5).
 */
export class AuthStack extends cdk.Stack {
  readonly userPool: cognito.UserPool;
  readonly webClient: cognito.UserPoolClient;

  constructor(scope: Construct, id: string, props: cdk.StackProps) {
    super(scope, id, props);

    this.userPool = new cognito.UserPool(this, 'UserPool', {
      userPoolName: 'inside-sales-copilot-users',
      selfSignUpEnabled: false,
      signInAliases: { email: true },
      signInCaseSensitive: false,
      standardAttributes: { email: { required: true, mutable: true } },
      customAttributes: { bu: new cognito.StringAttribute({ minLen: 1, maxLen: 32, mutable: true }) },
      passwordPolicy: {
        minLength: 12,
        requireLowercase: true,
        requireUppercase: true,
        requireDigits: true,
        requireSymbols: true,
        tempPasswordValidity: cdk.Duration.days(1),
      },
      accountRecovery: cognito.AccountRecovery.NONE, // an admin resets passwords; no email flows needed
      mfa: cognito.Mfa.OFF,
      featurePlan: cognito.FeaturePlan.LITE,
      removalPolicy: cdk.RemovalPolicy.DESTROY, // hackathon environment, demo users only
    });

    this.webClient = this.userPool.addClient('WebClient', {
      userPoolClientName: 'inside-sales-copilot-web',
      generateSecret: false,
      authFlows: { userSrp: true },
      disableOAuth: true,
      preventUserExistenceErrors: true,
      idTokenValidity: cdk.Duration.hours(1),
      accessTokenValidity: cdk.Duration.hours(1),
      refreshTokenValidity: cdk.Duration.minutes(60),
      enableTokenRevocation: true,
      readAttributes: new cognito.ClientAttributes()
        .withStandardAttributes({ email: true, emailVerified: true })
        .withCustomAttributes('bu'),
      // custom:bu is deliberately missing here: only the admin seed script can set it.
      writeAttributes: new cognito.ClientAttributes().withStandardAttributes({ email: true }),
    });

    new cdk.CfnOutput(this, 'UserPoolId', { value: this.userPool.userPoolId });
    new cdk.CfnOutput(this, 'UserPoolClientId', { value: this.webClient.userPoolClientId });
  }
}
