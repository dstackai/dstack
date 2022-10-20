package local

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"strings"
	"sync"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatchlogs"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatchlogs/types"
	"github.com/dstackai/dstackai/runner/internal/gerrors"
	"github.com/dstackai/dstackai/runner/internal/log"
)

var defaultFlushInterval = 250 * time.Millisecond

type Logger struct {
	cwl           *cloudwatchlogs.Client
	flushInterval time.Duration
	seqToken      *string
	logGroup      string
	logStream     string
	logEvents     []types.InputLogEvent
	mu            sync.Mutex
	logCh         chan LogMesage
	jobID         string
}
type Config struct {
	JobID         string
	Region        string
	FlushInterval time.Duration
}

type LogMesage struct {
	JobID  string `json:"job_id"`
	Log    string `json:"log"`
	Source string `json:"source"`
}

func (lm *LogMesage) String() string {
	logJson, err := json.Marshal(lm)
	if err != nil {
		return ""
	}
	return string(logJson)
}

func NewCloudwatch(cfg *Config) (*Logger, error) {
	awsConfig, err := config.LoadDefaultConfig(
		context.Background(),
		config.WithRegion(cfg.Region),
	)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	awsConfig.RetryMode = aws.RetryModeStandard
	awsConfig.ClientLogMode = aws.LogRequestEventMessage | aws.LogResponseEventMessage
	awsConfig.RetryMaxAttempts = 10
	client := cloudwatchlogs.NewFromConfig(awsConfig)
	l := &Logger{
		cwl:           client,
		flushInterval: cfg.FlushInterval,
		logEvents:     make([]types.InputLogEvent, 0),
		mu:            sync.Mutex{},
		logCh:         make(chan LogMesage, 100),
		jobID:         cfg.JobID,
	}
	if l.flushInterval <= 0 {
		l.flushInterval = defaultFlushInterval
	}

	return l, nil
}
func (l *Logger) checkStreamExists(ctx context.Context) error {
	_, err := l.cwl.CreateLogStream(ctx, &cloudwatchlogs.CreateLogStreamInput{
		LogGroupName:  aws.String(l.logGroup),
		LogStreamName: aws.String(l.logStream),
	})
	if err != nil {
		var awsErr *types.ResourceAlreadyExistsException
		if errors.As(err, &awsErr) {
			return nil
		}
		return gerrors.Wrap(err)
	}

	return nil
}

func (l *Logger) checkStreamExistsDeprecated(ctx context.Context) error {
	resp, err := l.cwl.DescribeLogStreams(ctx, &cloudwatchlogs.DescribeLogStreamsInput{
		LogGroupName: aws.String(l.logGroup),
	})
	if err != nil {
		return gerrors.Wrap(err)
	}
	for _, logStream := range resp.LogStreams {
		if *logStream.LogStreamName == l.logStream {
			l.seqToken = logStream.UploadSequenceToken
			return nil
		}
	}
	_, err = l.cwl.CreateLogStream(ctx, &cloudwatchlogs.CreateLogStreamInput{
		LogGroupName:  aws.String(l.logGroup),
		LogStreamName: aws.String(l.logStream),
	})

	return nil
}
func (l *Logger) checkGroupExists(_ context.Context) error {
	/*	log.Trace(ctx, "check group exist", "group", l.logGroup)
		_, err := l.cwl.CreateLogGroup(ctx, &cloudwatchlogs.CreateLogGroupInput{
			LogGroupName: aws.String(l.logGroup),
		})
		if err != nil {
			var awsErr *types.ResourceAlreadyExistsException
			if errors.As(err, &awsErr) {
				return nil
			}
			return gerrors.Wrap(err)
		}

	*/

	return nil
}
func (l *Logger) checkGroupExistsDeprecated(ctx context.Context) error {
	log.Trace(ctx, "check group exist", "group", l.logGroup)
	resp, err := l.cwl.DescribeLogGroups(ctx, &cloudwatchlogs.DescribeLogGroupsInput{
		LogGroupNamePrefix: aws.String(l.logGroup),
	})
	if err != nil {
		return gerrors.Wrap(err)
	}

	for _, logGroup := range resp.LogGroups {
		if *logGroup.LogGroupName == l.logGroup {
			return nil
		}
	}

	_, err = l.cwl.CreateLogGroup(ctx, &cloudwatchlogs.CreateLogGroupInput{
		LogGroupName: aws.String(l.logGroup),
	})
	if err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}
func (l *Logger) publishButch(ctx context.Context) error {
	if len(l.logEvents) == 0 {
		return nil
	}
	var err error
	input := cloudwatchlogs.PutLogEventsInput{
		LogEvents:     l.logEvents,
		LogGroupName:  aws.String(l.logGroup),
		LogStreamName: aws.String(l.logStream),
		SequenceToken: l.seqToken,
	}
	resp, err := l.cwl.PutLogEvents(ctx, &input)
	if err != nil {
		var seqTokenError *types.InvalidSequenceTokenException
		if errors.As(err, &seqTokenError) {
			log.Info(ctx, "Invalid token. Refreshing")
			l.seqToken = seqTokenError.ExpectedSequenceToken
			return l.publishButch(ctx)
		}
		var alreadyAccErr *types.DataAlreadyAcceptedException
		if errors.As(err, &alreadyAccErr) {
			log.Info(ctx, "Data already accepted. Refreshing")
			l.seqToken = alreadyAccErr.ExpectedSequenceToken
			return l.publishButch(ctx)
		}
		return gerrors.Wrap(err)
	}
	if resp.NextSequenceToken != nil {
		l.seqToken = resp.NextSequenceToken
	}
	return nil
}

var newTicker = func(freq time.Duration) *time.Ticker {
	return time.NewTicker(freq)
}

func (l *Logger) Write(p []byte) (int, error) {
	var err error
	l.logCh <- LogMesage{
		JobID:  l.jobID,
		Log:    strings.TrimRight(string(p), "\n"),
		Source: "stdout",
	}
	return len(p), gerrors.Wrap(err)
}

func (l *Logger) Build(ctx context.Context, logGroup, logStream string) io.Writer {
	newLogger := &Logger{
		cwl:           l.cwl,
		flushInterval: l.flushInterval,
		logGroup:      logGroup,
		logStream:     logStream,
		logEvents:     make([]types.InputLogEvent, 0),
		mu:            sync.Mutex{},
		logCh:         make(chan LogMesage, 100),
		jobID:         l.jobID,
	}
	if err := newLogger.checkGroupExists(ctx); err != nil {
		log.Error(ctx, "unable to check group", "err", err)
		return nil
	}
	if err := newLogger.checkStreamExists(ctx); err != nil {
		log.Error(ctx, "unable to check stream", "err", err)
		return nil
	}
	go newLogger.WriteLogs(ctx)
	return newLogger
}

func (l *Logger) WriteLogs(ctx context.Context) {
	defer func() {
		if err := recover(); err != nil {
			fmt.Println("[PANIC]", err)
		}
	}()
	ticker := newTicker(l.flushInterval)
	for {
		select {
		case <-ctx.Done():
			err := l.publishButch(context.Background())
			if err != nil {
				fmt.Println(err.Error())
			}
			l.mu.Lock()
			l.logEvents = l.logEvents[:0]
			l.mu.Unlock()
			return
		case <-ticker.C:
			err := l.publishButch(ctx)
			if err != nil {
				fmt.Println(err.Error())
			}
			l.mu.Lock()
			l.logEvents = l.logEvents[:0]
			l.mu.Unlock()
		case event, ok := <-l.logCh:
			if !ok {
				err := l.publishButch(ctx)
				if err != nil {
					fmt.Println(err.Error())
				}
				l.mu.Lock()
				l.logEvents = l.logEvents[:0]
				l.mu.Unlock()
				fmt.Println("[ERROR] log channel closed")
				return
			}
			l.mu.Lock()
			l.logEvents = append(l.logEvents, types.InputLogEvent{
				Message:   aws.String(event.String()),
				Timestamp: aws.Int64(time.Now().UnixNano() / int64(time.Millisecond)),
			})
			l.mu.Unlock()
		}
	}
}
