from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User, Group
from django.utils import timezone
from django.shortcuts import get_object_or_404, render
from rest_framework import status
from rest_framework.authentication import BasicAuthentication, SessionAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView

from logistics.permissions import is_driver, is_owner, IsOwnerPermission, IsDriverPermission, IsOwnerOrDriverPermission
from .forms import SignUpForm, LoginForm, FleetAddForm, FleetInviteDismissForm, PendingFleetAddToFleet, DriverAddTripForm, DriverReportProblemForm, \
    DriverAcceptTripForm
from .models import Fleet, Driver, Owner, DriverStats, Trip
from .serializers import FleetSerializer, DriverSerializer, TripSerializer


class CsrfExemptSessionAuthentication(SessionAuthentication):

    def enforce_csrf(self, request):
        return  # To not perform the csrf check previously happening


class SignUp(APIView):
    def post(self, request):
        form = SignUpForm(request.data)
        if form.is_valid():
            try:
                user = User.objects.create_user(username=form.cleaned_data["login"], email=form.cleaned_data["email"], password=form.cleaned_data["password"])
                if form.cleaned_data["role"] == "1" :
                    user.groups.add(Group.objects.get_or_create(name='OWNER')[0])
                    owner = Owner.objects.create(user=user, first_name=form.cleaned_data["first_name"], last_name=form.cleaned_data["last_name"])
                    user.save()
                    owner.save()
                else:
                    user.groups.add(Group.objects.get_or_create(name='DRIVER')[0])
                    driver = Driver.objects.create(user=user, first_name=form.cleaned_data["first_name"], last_name=form.cleaned_data["last_name"])
                    driver_stats = DriverStats.objects.create(driver=driver)
                    user.save()
                    driver.save()
                    driver_stats.save()
                return Response({"status": "ok"}, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({"status": "error", "errors": [str(e)]}, status=status.HTTP_409_CONFLICT)
        else:
            return Response({"status": "error", "errors": ["Invalid post parameters"]}, status=status.HTTP_400_BAD_REQUEST)


class Auth(APIView):
    def post(self, request):
        if not request.user.is_anonymous():
            return Response({"status": "error", "errors": ["Already login"]}, status=status.HTTP_409_CONFLICT)
        form = LoginForm(request.data)
        if form.is_valid():
            try:
                user = authenticate(username=form.cleaned_data["login"], password=form.cleaned_data["password"])
                if user is not None:
                    if user.is_active:
                        login(request, user)
                        return Response({"status": "ok"}, status=status.HTTP_200_OK)
                    else:
                        return Response({"status": "error"}, status=status.HTTP_409_CONFLICT)
            except Exception as e:
                return Response({"status": "error", "errors": [str(e)]}, status=status.HTTP_409_CONFLICT)
        else:
            return Response({"status": "error", "errors": ["Invalid post parameters"]}, status=status.HTTP_400_BAD_REQUEST)


class Logout(APIView):
    def get(self, request):
        if request.user.is_anonymous():
            return Response({"status": "error", "errors": ["Not authorized"]}, status=status.HTTP_409_CONFLICT)
        else:
            logout(request)
            return Response({"status": "ok"}, status=status.HTTP_200_OK)


class FleetList(APIView):
    permission_classes = (IsOwnerOrDriverPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def get(self, request):
        if is_owner(request.user):
            fleets = Fleet.objects.filter(owner=request.user.owner)
            serialized_fleets = FleetSerializer(fleets, many=True)
            return Response(serialized_fleets.data, status=status.HTTP_200_OK)
        elif is_driver(request.user):
            fleets = request.user.driver.fleets
            serialized_fleets = FleetSerializer(fleets, many=True)
            return Response(serialized_fleets.data, status=status.HTTP_200_OK)
        else:
            return Response({"status": "error", "errors": ["Not authorized"]}, status=status.HTTP_400_BAD_REQUEST)

    def post(self, request):
        current_user = request.user
        print(current_user)
        form = FleetAddForm(request.data)
        owner = request.user.owner
        if form.is_valid():
            try:
                fleet = form.save(commit=False)
                fleet.owner = owner
                fleet.save()
                print(fleet.name, fleet.description, fleet.owner, fleet.id)
                return Response({"status": "ok", "fleet_id": fleet.id}, status=status.HTTP_201_CREATED)
            except:
                return Response({"status": "error"}, status=status.HTTP_409_CONFLICT)
        else:
            return Response({"status": "error"}, status=status.HTTP_400_BAD_REQUEST)


class DriversByFleet(APIView):
    permission_classes = (IsOwnerPermission,)

    def get(self, request, fleet_id):
        if Fleet.objects.get(pk=fleet_id) in Fleet.objects.filter(owner=request.user.owner):
            drivers = Driver.objects.filter(fleets=fleet_id)
            serialized_drivers = DriverSerializer(drivers, many=True)
            return Response(serialized_drivers.data, status=status.HTTP_200_OK)
        else:
            return Response({"status": "error", "errors": ["Wrong fleet_id"]}, status=status.HTTP_409_CONFLICT)


class PendingDriversByFleet(APIView):
    permission_classes = (IsOwnerPermission,)

    def get(self, request, fleet_id):
        if Fleet.objects.get(pk=fleet_id) in Fleet.objects.filter(owner=request.user.owner):
            drivers = Driver.objects.exclude(fleets=fleet_id).exclude(pending_fleets=fleet_id)
            serialized_drivers = DriverSerializer(drivers, many=True)
            return Response(serialized_drivers.data, status=status.HTTP_200_OK)
        else:
            return Response({"status": "error", "errors": ["Wrong fleet_id"]}, status=status.HTTP_409_CONFLICT)


class FleetByIdView(APIView):
    permission_classes = (IsOwnerPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def get(self, request, fleet_id):
        fleet = Fleet.objects.get(id=fleet_id)
        if fleet in Fleet.objects.filter(owner=request.user.owner):
            serialized_fleet = FleetSerializer(fleet, many=False)
            return Response(serialized_fleet.data, status=status.HTTP_200_OK)
        else:
            return Response({"status": "error"}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, fleet_id):
        fleet_for_delete = Fleet.objects.get(id=fleet_id)
        if fleet_for_delete in Fleet.objects.filter(owner=request.user.owner):
            fleet_for_delete.delete()
            return Response({"status": "ok"}, status=status.HTTP_200_OK)
        else:
            return Response({"status": "error"}, status=status.HTTP_400_BAD_REQUEST)


class FleetInvite(APIView):
    permission_classes = (IsOwnerPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def post(self, request, fleet_id):
        form_invite = FleetInviteDismissForm(request.data)
        if form_invite.is_valid():
            try:
                fleet = Fleet.objects.get(id=fleet_id)
                if fleet in Fleet.objects.filter(owner=request.user.owner):
                    ids = form_invite.cleaned_data.get('driver_id')
                    for driver_id in ids.split(sep=','):
                        if driver_id != '':
                            driver = Driver.objects.get(id=driver_id)
                            driver.fleets.add(fleet)
                            driver.save()
                    return Response({"status": "ok"}, status=status.HTTP_200_OK)
                else:
                    return Response({"status": "error", "errors": ["Not owner of fleet"]}, status=status.HTTP_409_CONFLICT)
            except Exception as e:
                return Response({"status": "error", "errors": [str(e)]}, status=status.HTTP_409_CONFLICT)
        else:
            return Response({"status": "error"}, status=status.HTTP_400_BAD_REQUEST)


class FleetDismiss(APIView):
    permission_classes = (IsOwnerPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def post(self, request, fleet_id):
        form_dismiss = FleetInviteDismissForm(request.data)
        if form_dismiss.is_valid():
            try:
                fleet = Fleet.objects.get(id=fleet_id)
                if fleet in Fleet.objects.filter(owner=request.user.owner):
                    id = form_dismiss.cleaned_data.get('driver_id')
                    driver = Driver.objects.get(id=id)
                    driver.fleets.remove(fleet)
                    driver.save()
                    print(fleet.id, id, driver.id)
                    return Response({"status": "ok"}, status=status.HTTP_200_OK)
                else:
                    return Response({"status": "error", "errors": ["Not owner of fleet"]}, status=status.HTTP_409_CONFLICT)
            except:
                return Response({"status": "error"}, status=status.HTTP_409_CONFLICT)
        else:
            return Response({"status": "error"}, status=status.HTTP_400_BAD_REQUEST)


# DRIVER API
class DriverPendingFleets(APIView):
    permission_classes = (IsDriverPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def get(self, request):
        #GET /api/driver/pending_fleets/
        pending_fleets = request.user.driver.pending_fleets
        serialized_pending_fleets = FleetSerializer(pending_fleets, many=True)
        return Response(serialized_pending_fleets.data, status=status.HTTP_200_OK)


class DriverPendingFleetsAccept(APIView):
    permission_classes = (IsDriverPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def post(self, request):
        # POST /api/driver/pending_fleets/accept/
        form_pending_to_fleet = PendingFleetAddToFleet(request.data)
        if form_pending_to_fleet.is_valid():
            try:
                fleets = request.user.driver.fleets
                pending_fleets = request.user.driver.pending_fleets
                print(fleets.all())
                print(pending_fleets.all())
                ids = form_pending_to_fleet.cleaned_data.get('fleet_id')
                for fleet_id in ids.split(sep=','):
                    waited_fleet = None
                    try:
                        waited_fleet = Fleet.objects.get(id=fleet_id)
                        print(waited_fleet.id)
                    except:
                        pass
                    if waited_fleet is not None:
                        if waited_fleet in pending_fleets.all():
                            fleets.add(waited_fleet)
                            pending_fleets.remove(waited_fleet)
                print(fleets.all())
                print(pending_fleets.all())
                return Response({"status": "ok"}, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({"status": "error", "errors": [str(e)]}, status=status.HTTP_409_CONFLICT)
        else:
            return Response({"status": "error"}, status=status.HTTP_400_BAD_REQUEST)


class DriverPendingFleetsDecline(APIView):
    permission_classes = (IsDriverPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def post(self, request):
        # POST /api/driver/pending_fleets/decline/
        pass


class DriverFleets(APIView):
    permission_classes = (IsDriverPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def get(self, request):
        #GET /api/driver/fleets/
        fleets = request.user.driver.fleets
        serialized_fleets = FleetSerializer(fleets, many=True)
        return Response(serialized_fleets.data, status=status.HTTP_200_OK)


class DriverFleetAvailableTrips(APIView):
    permission_classes = (IsDriverPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def get(self, request, fleet_id):
        #GET /api/driver/fleet/<fleet_id>/available_trips/
        try:
            fleet = Fleet.objects.get(id=fleet_id)
        except:
            return Response({"status": "error"}, status=status.HTTP_409_CONFLICT)
        trips = Trip.objects.none()
        if fleet in request.user.driver.fleets.all():
            trips = Trip.objects.filter(fleet=fleet, driver=None, is_finished=False)
        serialized_trips = TripSerializer(trips, many=True)
        return Response(serialized_trips.data, status=status.HTTP_200_OK)


class DriverAvailableTrips(APIView):
    permission_classes = (IsDriverPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def get(self, request):
        #GET /api/driver/available_trips/
        fleets = request.user.driver.fleets
        trips = Trip.objects.none()
        for fleet in fleets.all():
            trips_add = Trip.objects.filter(fleet=fleet, driver=None, is_finished=False)
            trips = trips | trips_add
        serialized_trips = TripSerializer(trips, many=True)
        return Response(serialized_trips.data, status=status.HTTP_200_OK)


class DriverFleetTrips(APIView):
    permission_classes = (IsDriverPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def get(self, request, fleet_id):
        #GET /api/driver/fleet/<fleet_id>/trips/
        try:
            fleet = Fleet.objects.get(id=fleet_id)
            print(fleet)
        except:
            return Response({"status": "error"}, status=status.HTTP_409_CONFLICT)
        trips = Trip.objects.none()
        if fleet in request.user.driver.fleets.all():
            trips = Trip.objects.filter(fleet=fleet, driver=request.user.driver)
        serialized_trips = TripSerializer(trips, many=True)
        return Response(serialized_trips.data, status=status.HTTP_200_OK)


class DriverTrips(APIView):
    permission_classes = (IsDriverPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def get(self, request):
        #GET /api/driver/trips/
        fleets = request.user.driver.fleets
        trips = Trip.objects.none()
        for fleet in fleets.all():
            trips_add = Trip.objects.filter(fleet=fleet, driver=request.user.driver)
            trips = trips | trips_add
        serialized_trips = TripSerializer(trips, many=True)
        return Response(serialized_trips.data, status=status.HTTP_200_OK)


class DriverAcceptTrip(APIView):
    permission_classes = (IsDriverPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def post(self, request):
        #POST /api/driver/accept_trip/
        driver = request.user.driver
        trip_id_form = DriverAcceptTripForm(request.data)
        if not trip_id_form.is_valid():
            return Response({"status": "trip_id_form not valid"}, status=status.HTTP_400_BAD_REQUEST)
        trip_id = trip_id_form.cleaned_data.get('trip_id')
        trip = get_object_or_404(Trip, id=trip_id)
        try:
            print(trip, trip.id, trip.fleet, trip.driver, trip.is_finished)
            print(driver, driver.fleets.all())
            if trip.driver == driver and trip.is_finished:
                return Response({"status": "error", "errors": "You have already been finished this trip"},
                                status=status.HTTP_409_CONFLICT)
            elif trip.driver == driver:
                # TODO Redirect to page with current trip
                return Response({"status": "error", "errors": "It's your current trip"},
                                status=status.HTTP_409_CONFLICT)
            elif trip.driver is not None:
                return Response({"status": "error", "errors": "This trip has already been accepted"},
                                status=status.HTTP_409_CONFLICT)
            elif trip.is_finished:
                return Response({"status": "error", "errors": "This trip is finished but don't have a driver!!!"},
                                status=status.HTTP_409_CONFLICT)
            if trip.fleet not in driver.fleets.all():
                return Response({"status": "error", "errors": "You are not a member in that fleet"},
                                status=status.HTTP_409_CONFLICT)
            if Trip.objects.filter(driver=driver, is_finished=False).exists():
                # TODO Redirect to page with current trip
                return Response({"status": "error", "errors": "You have already accepted current trip"},
                                status=status.HTTP_409_CONFLICT)
            # TODO Change 1 to static variable
            if trip.problem is not 1:
                return Response({"status": "error", "errors": "The trip has a problem"},
                                status=status.HTTP_409_CONFLICT)
            trip.driver = driver
            trip.save()
            return Response({"status": "ok"}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"status": "error", "errors": [str(e)]}, status=status.HTTP_409_CONFLICT)


class DriverAddTrip(APIView):
    permission_classes = (IsDriverPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def post(self, request, fleet_id):
        #POST /api/driver/fleet/<fleet_id>/add_trip/
        form_driver_add_trip = DriverAddTripForm(request.data)
        print(request.data)
        #print(form_driver_add_trip.cleaned_data)
        if form_driver_add_trip.is_valid():
            try:
                fleet = get_object_or_404(Fleet, id=fleet_id)
                print(fleet)
                trip = form_driver_add_trip.save(commit=False)
                trip.start_date = timezone.now()
                # Добавить, когда водитель сможет выбирать currentTrip
                # trip.driver = request.user.driver
                # TODO добавить проверку, является ли пользователь владельцем, создающим поездку
                if fleet in request.user.driver.fleets.all():
                    trip.fleet = fleet
                else:
                    return Response({"status": "error", "errors": "You are not a member in that fleet"},
                                    status=status.HTTP_409_CONFLICT)
                trip.save()
                trip.name = str(fleet.name)+"#"+str(trip.id)
                trip.save()
                print(trip.name, trip.description, trip.driver, trip.fleet, trip.start_date, trip.id)
                return Response({"status": "ok"}, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({"status": "error", "errors": [str(e)]}, status=status.HTTP_409_CONFLICT)
        else:
            return Response({"status": "error"}, status=status.HTTP_400_BAD_REQUEST)


class DriverCurrentTrip(APIView):
    permission_classes = (IsDriverPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def get(self, request):
        #GET GET /api/driver/current_trip/
        try:
            trip = Trip.objects.get(driver=request.user.driver, is_finished=False)
        except:
            return Response({"status": "error", "errors": "You have not current trip"},
                            status=status.HTTP_409_CONFLICT)
        print(trip, trip.id, trip.fleet)
        try:
            serialized_trip = TripSerializer(trip)
            return Response(serialized_trip.data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"status": "error", "errors": [str(e)]}, status=status.HTTP_409_CONFLICT)


class DriverReportProblem(APIView):
    permission_classes = (IsDriverPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def post(self, request):
        #POST /api/driver/report_problem/
        try:
            trip = Trip.objects.get(driver=request.user.driver, is_finished=False)
        except:
            return Response({"status": "error", "errors": "You have not current trip"},
                            status=status.HTTP_409_CONFLICT)
        form_report_problem = DriverReportProblemForm(request.data, instance=trip)
        if form_report_problem.is_valid():
            try:
                print(trip.problem)
                form_report_problem.save()
                print(trip.problem)
                return Response({"status": "ok"}, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({"status": "error", "errors": [str(e)]}, status=status.HTTP_409_CONFLICT)
        else:
            return Response({"status": "error"}, status=status.HTTP_400_BAD_REQUEST)


class DriverFinishTrip(APIView):
    permission_classes = (IsDriverPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def post(self, request):
        #POST /api/driver/finish_trip/
        try:
            trip = Trip.objects.get(driver=request.user.driver, is_finished=False)
        except:
            return Response({"status": "error", "errors": "You have not current trip"},
                            status=status.HTTP_409_CONFLICT)
        print(trip, trip.id, trip.fleet)
        try:
            trip.is_finished = True
            trip.save()
            return Response({"status": "ok"}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"status": "error", "errors": [str(e)]}, status=status.HTTP_409_CONFLICT)
