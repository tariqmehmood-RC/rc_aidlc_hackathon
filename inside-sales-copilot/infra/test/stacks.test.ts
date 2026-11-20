import { Match } from 'aws-cdk-lib/assertions';
import { asList, statements, template } from './helpers';

// --- 5.1 AuthStack -----------------------------------------------------------------------------
describe('AuthStack', () => {
  const t = template('AuthStack');

  test('no self sign-up, email sign-in, custom:bu attribute, strong passwords', () => {
    t.hasResourceProperties('AWS::Cognito::UserPool', {
      AdminCreateUserConfig: { AllowAdminCreateUserOnly: true },
      UsernameAttributes: ['email'],
      Schema: Match.arrayWith([Match.objectLike({ Name: 'bu', AttributeDataType: 'String', Mutable: true })]),
      Policies: { PasswordPolicy: Match.objectLike({ MinimumLength: 12, RequireSymbols: true }) },
    });
  });

  test('app client: no secret, SRP only, 1 hour tokens, hides user existence', () => {
    t.hasResourceProperties('AWS::Cognito::UserPoolClient', {
      GenerateSecret: false,
      ExplicitAuthFlows: Match.arrayWith(['ALLOW_USER_SRP_AUTH']),
      IdTokenValidity: 60,
      AccessTokenValidity: 60,
      TokenValidityUnits: { IdToken: 'minutes', AccessToken: 'minutes', RefreshToken: 'minutes' },
      PreventUserExistenceErrors: 'ENABLED',
    });
    const client = Object.values(t.findResources('AWS::Cognito::UserPoolClient'))[0] as any;
    expect(client.Properties.ExplicitAuthFlows).not.toContain('ALLOW_USER_PASSWORD_AUTH');
    expect(client.Properties.ExplicitAuthFlows).not.toContain('ALLOW_ADMIN_USER_PASSWORD_AUTH');
  });

  test('the app client can read custom:bu but never write it', () => {
    const client = Object.values(t.findResources('AWS::Cognito::UserPoolClient'))[0] as any;
    expect(client.Properties.ReadAttributes).toContain('custom:bu');
    expect(client.Properties.WriteAttributes).not.toContain('custom:bu');
  });

  test('outputs the pool and client ids for config.json and the seed script', () => {
    t.hasOutput('UserPoolId', {});
    t.hasOutput('UserPoolClientId', {});
  });
});

// --- 5.2 DataStack ----------------------------------------------------------------------------------
describe('DataStack', () => {
  const t = template('DataStack');

  test('three on-demand tables with the keys the backend uses', () => {
    t.resourceCountIs('AWS::DynamoDB::Table', 3);
    t.hasResourceProperties('AWS::DynamoDB::Table', {
      KeySchema: [{ AttributeName: 'briefId', KeyType: 'HASH' }],
      BillingMode: 'PAY_PER_REQUEST',
      TimeToLiveSpecification: { AttributeName: 'expiresAt', Enabled: true },
      GlobalSecondaryIndexes: Match.arrayWith([
        Match.objectLike({ IndexName: 'byUser', KeySchema: [{ AttributeName: 'userId', KeyType: 'HASH' }, { AttributeName: 'createdAt', KeyType: 'RANGE' }], Projection: { ProjectionType: 'ALL' } }),
        Match.objectLike({ IndexName: 'byQueue', KeySchema: [{ AttributeName: 'queueKey', KeyType: 'HASH' }, { AttributeName: 'queuedAt', KeyType: 'RANGE' }], Projection: { ProjectionType: 'KEYS_ONLY' } }),
      ]),
    });
    t.hasResourceProperties('AWS::DynamoDB::Table', {
      KeySchema: [{ AttributeName: 'userId', KeyType: 'HASH' }, { AttributeName: 'ruleId', KeyType: 'RANGE' }],
      BillingMode: 'PAY_PER_REQUEST',
    });
    t.hasResourceProperties('AWS::DynamoDB::Table', {
      KeySchema: [{ AttributeName: 'companyDomain', KeyType: 'HASH' }],
      TimeToLiveSpecification: { AttributeName: 'expiresAt', Enabled: true },
    });
  });

  test('tables are encrypted', () => {
    for (const table of Object.values(t.findResources('AWS::DynamoDB::Table')) as any[]) {
      expect(table.Properties.SSESpecification).toEqual({ SSEEnabled: true });
    }
  });

  test('standard queue, 1080 s visibility, dead-letter queue after 3 receives, TLS only', () => {
    t.resourceCountIs('AWS::SQS::Queue', 2);
    t.hasResourceProperties('AWS::SQS::Queue', {
      VisibilityTimeout: 1080,
      RedrivePolicy: { deadLetterTargetArn: Match.anyValue(), maxReceiveCount: 3 },
      SqsManagedSseEnabled: true,
    });
    t.hasResourceProperties('AWS::SQS::Queue', { MessageRetentionPeriod: 14 * 24 * 3600 });
    t.hasResourceProperties('AWS::SQS::QueuePolicy', {
      PolicyDocument: { Statement: Match.arrayWith([Match.objectLike({ Effect: 'Deny', Condition: { Bool: { 'aws:SecureTransport': 'false' } } })]) },
    });
    for (const q of Object.values(t.findResources('AWS::SQS::Queue')) as any[]) expect(q.Properties.FifoQueue).toBeUndefined();
  });
});

// --- 5.4 ApiStack ----------------------------------------------------------------------------------------
describe('ApiStack', () => {
  const t = template('ApiStack');
  const fns = t.findResources('AWS::Lambda::Function');
  const workerId = Object.keys(fns).find((k) => (fns[k] as any).Properties.Handler === 'backend.src.handlers.worker.handler')!;
  const roleOf = (fnId: string) => (fns[fnId] as any).Properties.Role['Fn::GetAtt'][0];
  const policiesOfRole = (roleId: string) =>
    statements(t).filter((s) => {
      const policy = (t.findResources('AWS::IAM::Policy') as any)[s._policy];
      return policy.Properties.Roles.some((r: any) => r.Ref === roleId);
    });

  test('11 routes, every one behind the Cognito JWT authorizer', () => {
    const routes = Object.values(t.findResources('AWS::ApiGatewayV2::Route')) as any[];
    expect(routes.map((r) => r.Properties.RouteKey).sort()).toEqual([
      'DELETE /api/rules/{ruleId}', 'GET /api/briefs', 'GET /api/briefs/{id}', 'GET /api/case-studies', 'GET /api/rules',
      'POST /api/briefs', 'POST /api/briefs/{id}/approve', 'POST /api/briefs/{id}/confirm', 'POST /api/briefs/{id}/retry',
      'POST /api/briefs/{id}/rules', 'PUT /api/briefs/{id}',
    ]);
    for (const r of routes) expect(r.Properties.AuthorizationType).toBe('JWT');
    t.hasResourceProperties('AWS::ApiGatewayV2::Authorizer', {
      AuthorizerType: 'JWT',
      IdentitySource: ['$request.header.Authorization'],
      JwtConfiguration: { Audience: Match.anyValue(), Issuer: Match.anyValue() },
    });
  });

  test('the stage throttles requests', () => {
    t.hasResourceProperties('AWS::ApiGatewayV2::Stage', {
      StageName: '$default',
      DefaultRouteSettings: { ThrottlingRateLimit: 20, ThrottlingBurstLimit: 40 },
    });
  });

  test('all functions: Python 3.12 on arm64, tracing, 14-day logs', () => {
    expect(Object.keys(fns)).toHaveLength(10);
    for (const fn of Object.values(fns) as any[]) {
      expect(fn.Properties.Runtime).toBe('python3.12');
      expect(fn.Properties.Architectures).toEqual(['arm64']);
      expect(fn.Properties.TracingConfig).toEqual({ Mode: 'Active' });
    }
    const groups = Object.values(t.findResources('AWS::Logs::LogGroup')) as any[];
    expect(groups).toHaveLength(10);
    for (const g of groups) expect(g.Properties.RetentionInDays).toBe(14);
  });

  test('the worker runs one at a time, one message at a time, with a 180 s timeout', () => {
    const worker = (fns[workerId] as any).Properties;
    expect(worker.ReservedConcurrentExecutions).toBe(1);
    expect(worker.Timeout).toBe(180);
    expect(worker.Environment.Variables).toMatchObject({
      BEDROCK_MODEL_HAIKU: 'us.anthropic.claude-haiku-4-5-20251001-v1:0',
      BEDROCK_MODEL_SONNET: 'us.anthropic.claude-sonnet-5',
      BRIEF_MODEL: 'haiku',
    });
    t.hasResourceProperties('AWS::Lambda::EventSourceMapping', { BatchSize: 1 });
  });

  test('only the worker can call Bedrock, and only the two configured models', () => {
    const bedrock = statements(t).filter((s) => asList(s.Action).some((a) => a.startsWith('bedrock:')));
    expect(bedrock).toHaveLength(1);
    expect(policiesOfRole(roleOf(workerId))).toContainEqual(expect.objectContaining({ Action: 'bedrock:InvokeModel' }));
    const resources = JSON.stringify(bedrock[0].Resource);
    expect(resources).toContain('inference-profile/us.anthropic.claude-haiku-4-5-20251001-v1:0');
    expect(resources).toContain('inference-profile/us.anthropic.claude-sonnet-5');
    for (const r of ['us-east-1', 'us-east-2', 'us-west-2']) {
      expect(resources).toContain(`arn:aws:bedrock:${r}::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0`);
      expect(resources).toContain(`arn:aws:bedrock:${r}::foundation-model/anthropic.claude-sonnet-5`);
    }
    expect(resources).not.toMatch(/foundation-model\/\*|"\*"/);
    for (const fnId of Object.keys(fns).filter((k) => k !== workerId)) {
      const acts = policiesOfRole(roleOf(fnId)).flatMap((s) => asList(s.Action));
      expect(acts.some((a) => a.startsWith('bedrock:'))).toBe(false);
    }
  });

  test('no wildcard resources except where AWS requires them (X-Ray)', () => {
    for (const s of statements(t)) {
      if (asList(s.Resource as any).includes('*')) {
        expect(asList(s.Action).every((a) => a.startsWith('xray:'))).toBe(true);
      }
      expect(asList(s.Action).some((a) => a === '*' || a.endsWith(':*'))).toBe(false);
    }
  });

  test('API functions only send to the queue; only the worker reads from it', () => {
    for (const fnId of Object.keys(fns)) {
      const acts = policiesOfRole(roleOf(fnId)).flatMap((s) => asList(s.Action));
      if (fnId === workerId) {
        expect(acts).toEqual(expect.arrayContaining(['sqs:ReceiveMessage', 'sqs:DeleteMessage']));
        expect(acts).not.toContain('sqs:SendMessage');
      } else {
        expect(acts.filter((a) => a.startsWith('sqs:')).every((a) => a === 'sqs:SendMessage')).toBe(true);
      }
    }
  });

  test('DynamoDB access uses exact actions, never Scan or wildcards', () => {
    const ddb = statements(t).flatMap((s) => asList(s.Action)).filter((a) => a.startsWith('dynamodb:'));
    expect(ddb.length).toBeGreaterThan(0);
    for (const a of ddb) expect(['dynamodb:GetItem', 'dynamodb:PutItem', 'dynamodb:UpdateItem', 'dynamodb:Query', 'dynamodb:DeleteItem']).toContain(a);
  });

  test('the case studies function has no data access at all', () => {
    const fnId = Object.keys(fns).find((k) => (fns[k] as any).Properties.Handler.endsWith('case_studies_handler'))!;
    const acts = policiesOfRole(roleOf(fnId)).flatMap((s) => asList(s.Action));
    expect(acts.filter((a) => a.startsWith('dynamodb:') || a.startsWith('sqs:'))).toEqual([]);
  });

  test('alarms: dead letters, worker errors, Bedrock throttling, API 5xx; plus a dashboard', () => {
    t.resourceCountIs('AWS::CloudWatch::Alarm', 4);
    t.hasResourceProperties('AWS::CloudWatch::Alarm', {
      MetricName: 'ApproximateNumberOfMessagesVisible', Threshold: 0, ComparisonOperator: 'GreaterThanThreshold',
    });
    t.hasResourceProperties('AWS::CloudWatch::Alarm', { MetricName: 'BedrockThrottled', Namespace: 'InsideSalesCopilot', Threshold: 5 });
    t.resourceCountIs('AWS::CloudWatch::Dashboard', 1);
  });
});

// --- 5.5 WebStack -------------------------------------------------------------------------------------------
describe('WebStack', () => {
  const t = template('WebStack');

  test('the bucket is private, encrypted, and TLS only', () => {
    t.hasResourceProperties('AWS::S3::Bucket', {
      PublicAccessBlockConfiguration: { BlockPublicAcls: true, BlockPublicPolicy: true, IgnorePublicAcls: true, RestrictPublicBuckets: true },
      BucketEncryption: Match.objectLike({}),
    });
    const policy = Object.values(t.findResources('AWS::S3::BucketPolicy'))[0] as any;
    const stmts = policy.Properties.PolicyDocument.Statement as any[];
    expect(stmts.some((s) => s.Effect === 'Deny' && s.Condition?.Bool?.['aws:SecureTransport'] === 'false')).toBe(true);
    for (const s of stmts.filter((x) => x.Effect === 'Allow')) {
      // only CloudFront (with this distribution's ARN) or the auto-delete cleanup role may read
      expect(JSON.stringify(s.Principal)).not.toBe('"*"');
      if (s.Principal?.Service === 'cloudfront.amazonaws.com') expect(s.Condition.StringEquals['AWS:SourceArn']).toBeDefined();
    }
  });

  test('CloudFront: HTTPS redirect for the site, HTTPS only and no caching for /api/*', () => {
    t.hasResourceProperties('AWS::CloudFront::Distribution', {
      DistributionConfig: Match.objectLike({
        DefaultRootObject: 'index.html',
        DefaultCacheBehavior: Match.objectLike({ ViewerProtocolPolicy: 'redirect-to-https' }),
        CacheBehaviors: [Match.objectLike({
          PathPattern: '/api/*',
          ViewerProtocolPolicy: 'https-only',
          CachePolicyId: '4135ea2d-6df8-44a3-9df3-4b5a84be39ad', // Managed-CachingDisabled
          AllowedMethods: Match.arrayWith(['PUT', 'POST', 'DELETE']),
        })],
        Origins: Match.arrayWith([Match.objectLike({ CustomOriginConfig: Match.objectLike({ OriginProtocolPolicy: 'https-only' }) })]),
      }),
    });
    t.resourceCountIs('AWS::CloudFront::OriginAccessControl', 1);
  });

  test('no custom error pages (they would hide API errors); the SPA rewrite is a function on the site only', () => {
    const dist = Object.values(t.findResources('AWS::CloudFront::Distribution'))[0] as any;
    expect(dist.Properties.DistributionConfig.CustomErrorResponses).toBeUndefined();
    expect(dist.Properties.DistributionConfig.DefaultCacheBehavior.FunctionAssociations).toHaveLength(1);
    expect(dist.Properties.DistributionConfig.CacheBehaviors[0].FunctionAssociations).toBeUndefined();
  });

  test('security headers: HSTS, CSP, no framing, no sniffing', () => {
    t.hasResourceProperties('AWS::CloudFront::ResponseHeadersPolicy', {
      ResponseHeadersPolicyConfig: {
        Name: Match.anyValue(),
        SecurityHeadersConfig: Match.objectLike({
          StrictTransportSecurity: Match.objectLike({ AccessControlMaxAgeSec: 31536000 }),
          ContentSecurityPolicy: Match.objectLike({ ContentSecurityPolicy: Match.stringLikeRegexp("default-src 'self'.*connect-src 'self' https://cognito-idp.us-east-1.amazonaws.com") }),
          FrameOptions: { FrameOption: 'DENY', Override: true },
          ContentTypeOptions: { Override: true },
        }),
      },
    });
  });

  test('outputs the site URL, bucket, and distribution for the deploy script', () => {
    t.hasOutput('SiteUrl', {});
    t.hasOutput('BucketName', {});
    t.hasOutput('DistributionId', {});
  });
});
